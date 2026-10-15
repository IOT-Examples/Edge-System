import logging
import os
from unittest.mock import patch, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app, send_averages_to_backend, build_backend_url, measurements

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_measurements():
    """Limpia las mediciones en memoria entre pruebas para evitar efectos secundarios."""
    measurements.clear()
    yield
    measurements.clear()


# ---------------------------------------------------------------------------
# 1. /health sigue funcionando
# ---------------------------------------------------------------------------
def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "edge"}


# ---------------------------------------------------------------------------
# 2. Recepción de medición válida del ESP32
# ---------------------------------------------------------------------------
def test_receive_measurement_valid():
    response = client.post("/measurements", json={
        "device_id": "esp32_001",
        "temperature": 25.6,
        "humidity": 63.2,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "esp32_001"
    assert data["samples"] == 1
    assert data["average_temperature"] == 25.6
    assert data["average_humidity"] == 63.2


# ---------------------------------------------------------------------------
# 3. Cálculo correcto de promedios con varias mediciones
# ---------------------------------------------------------------------------
def test_average_across_multiple_measurements():
    client.post("/measurements", json={"device_id": "esp32_001", "temperature": 20.0, "humidity": 50.0})
    client.post("/measurements", json={"device_id": "esp32_001", "temperature": 30.0, "humidity": 70.0})
    response = client.post("/measurements", json={"device_id": "esp32_001", "temperature": 25.0, "humidity": 60.0})
    assert response.status_code == 200
    data = response.json()
    assert data["samples"] == 3
    assert data["average_temperature"] == 25.0
    assert data["average_humidity"] == 60.0


# ---------------------------------------------------------------------------
# 4. Validación de rangos (rechaza valores fuera de rango)
# ---------------------------------------------------------------------------
def test_rejects_temperature_out_of_range():
    response = client.post("/measurements", json={
        "device_id": "esp32_001",
        "temperature": 100.0,  # fuera de [-40, 80]
        "humidity": 50.0,
    })
    assert response.status_code == 422


def test_rejects_humidity_out_of_range():
    response = client.post("/measurements", json={
        "device_id": "esp32_001",
        "temperature": 25.0,
        "humidity": 110.0,  # fuera de [0, 100]
    })
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 5. Envío de promedios al backend (mockeado)
# ---------------------------------------------------------------------------
@patch("main.httpx.post")
def test_send_averages_to_backend_success(mock_post, caplog):
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"
    os.environ["BACKEND_AVERAGES_PATH"] = "/api/v1/telemetry/averages"
    os.environ.pop("BACKEND_API_KEY", None)

    # Reconstruir URL con variables actualizadas
    url = build_backend_url()
    assert url == "https://back-example-ocx9.onrender.com/api/v1/telemetry/averages"

    caplog.set_level(logging.INFO)

    send_averages_to_backend({
        "device_id": "esp32_001",
        "samples": 1,
        "average_temperature": 25.6,
        "average_humidity": 63.2,
    })

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == url
    assert kwargs["json"]["device_id"] == "esp32_001"
    assert kwargs["json"]["samples"] == 1
    assert "X-API-Key" not in kwargs.get("headers", {})
    assert "enviados al backend correctamente" in caplog.text


@patch("main.httpx.post")
def test_send_averages_to_backend_with_api_key(mock_post):
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"
    os.environ["BACKEND_API_KEY"] = "test-secret-key"

    send_averages_to_backend({
        "device_id": "esp32_001",
        "samples": 1,
        "average_temperature": 25.6,
        "average_humidity": 63.2,
    })

    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["X-API-Key"] == "test-secret-key"


@patch("main.httpx.post")
def test_send_averages_to_backend_http_error(mock_post, caplog):
    """El backend responde con error HTTP (no éxito)."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 500
    mock_post.return_value = mock_response

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"

    send_averages_to_backend({
        "device_id": "esp32_001",
        "samples": 1,
        "average_temperature": 25.6,
        "average_humidity": 63.2,
    })

    assert "error" in caplog.text.lower()


@patch("main.httpx.post")
def test_send_averages_to_backend_timeout(mock_post, caplog):
    """Timeout de conexión: se registra sin romper el Edge."""
    mock_post.side_effect = httpx.TimeoutException("Timeout conectando al backend")

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"

    send_averages_to_backend({
        "device_id": "esp32_001",
        "samples": 1,
        "average_temperature": 25.6,
        "average_humidity": 63.2,
    })

    assert "timeout" in caplog.text.lower()


@patch("main.httpx.post")
def test_send_averages_to_backend_connection_error(mock_post, caplog):
    """Error de conexión: se registra sin romper el Edge."""
    mock_post.side_effect = httpx.ConnectError("No se pudo conectar")

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"

    send_averages_to_backend({
        "device_id": "esp32_001",
        "samples": 1,
        "average_temperature": 25.6,
        "average_humidity": 63.2,
    })

    assert "conexión" in caplog.text.lower() or "connect" in caplog.text.lower()


# ---------------------------------------------------------------------------
# 6. El Edge responde al ESP32 aunque el backend falle
# ---------------------------------------------------------------------------
@patch("main.httpx.post")
def test_edge_responds_when_backend_fails(mock_post):
    """El endpoint /measurements debe devolver 200 aunque el backend caiga."""
    mock_post.side_effect = Exception("Backend caído")

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"

    response = client.post("/measurements", json={
        "device_id": "esp32_001",
        "temperature": 20.0,
        "humidity": 50.0,
    })
    assert response.status_code == 200
    assert response.json()["device_id"] == "esp32_001"
    assert response.json()["samples"] == 1


@patch("main.httpx.post")
def test_edge_responds_when_backend_returns_500(mock_post):
    """El endpoint /measurements debe devolver 200 aunque el backend responda 500."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 500
    mock_post.return_value = mock_response

    os.environ["BACKEND_BASE_URL"] = "https://back-example-ocx9.onrender.com"

    response = client.post("/measurements", json={
        "device_id": "esp32_001",
        "temperature": 20.0,
        "humidity": 50.0,
    })
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 7. Sin BACKEND_BASE_URL configurada: se omite envío sin error
# ---------------------------------------------------------------------------
@patch("main.httpx.post")
def test_no_backend_url_skips_sending(mock_post, caplog):
    os.environ.pop("BACKEND_BASE_URL", None)

    send_averages_to_backend({
        "device_id": "esp32_001",
        "samples": 1,
        "average_temperature": 25.6,
        "average_humidity": 63.2,
    })

    mock_post.assert_not_called()
    assert "no configurada" in caplog.text

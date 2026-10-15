import os
import logging
from pydantic import BaseModel, Field
from fastapi import FastAPI
from collections import deque
from datetime import datetime, timezone
import httpx

app = FastAPI(title="IoT Edge System")

# Configuración de logging (sin secretos)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("edge")

# Conserva las últimas 5 mediciones en memoria
measurements = deque(maxlen=5)

# ---------------------------------------------------------------------------
# Configuración del backend IoT (desde variables de entorno, leída dinámicamente)
# ---------------------------------------------------------------------------


class SensorReading(BaseModel):
    device_id: str
    temperature: float = Field(ge=-40, le=80)
    humidity: float = Field(ge=0, le=100)


@app.get("/health")
def health():
    return {"status": "ok", "component": "edge"}


def _get_backend_config() -> tuple[str, str, str | None, float]:
    """Lee la configuración del backend desde variables de entorno."""
    base_url = os.getenv("BACKEND_BASE_URL", "").rstrip("/")
    averages_path = os.getenv("BACKEND_AVERAGES_PATH", "/api/v1/telemetry/averages")
    api_key = os.getenv("BACKEND_API_KEY", None)
    timeout = float(os.getenv("BACKEND_TIMEOUT", "5.0"))
    return base_url, averages_path, api_key, timeout


def build_backend_url() -> str:
    """Construye la URL completa del endpoint de promedios del backend."""
    base_url, averages_path, _, _ = _get_backend_config()
    if not base_url:
        return ""
    return f"{base_url}{averages_path}"


def send_averages_to_backend(result: dict) -> None:
    """Envía los promedios calculados al backend IoT.

    Nunca bloquea la respuesta al ESP32: cualquier error se registra y se ignora,
    permitiendo que el Edge siga atendiendo mediciones aunque el backend caiga.
    """
    base_url, averages_path, api_key, timeout = _get_backend_config()

    if not base_url:
        logger.warning("BACKEND_BASE_URL no configurada; se omite envío al backend.")
        return

    url = f"{base_url}{averages_path}"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = httpx.post(url, json=result, headers=headers, timeout=timeout)

        if response.is_success:
            logger.info(
                "Promedios enviados al backend correctamente (status=%s, device_id=%s)",
                response.status_code,
                result.get("device_id"),
            )
        else:
            # Respuesta de error limitada y segura: no se imprime el cuerpo completo
            # para evitar exponer datos internos o secretos del backend.
            logger.error(
                "Backend respondió con error (status=%s, url=%s)",
                response.status_code,
                url,
            )
    except httpx.TimeoutException:
        logger.error(
            "Timeout al enviar promedios al backend (url=%s). "
            "No se puede confirmar si el backend guardó el registro.",
            url,
        )
    except httpx.RequestError as exc:
        logger.error(
            "Error de conexión al enviar promedios al backend (url=%s): %s",
            url,
            type(exc).__name__,
        )
    except Exception as exc:  # noqa: BLE001 - evitar que cualquier fallo inesperado rompa el Edge
        logger.error(
            "Error inesperado al enviar promedios al backend: %s",
            type(exc).__name__,
        )


@app.post("/measurements")
def receive_measurement(reading: SensorReading):
    measurement = {
        **reading.model_dump(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    measurements.append(measurement)

    avg_temperature = sum(m["temperature"] for m in measurements) / len(measurements)
    avg_humidity = sum(m["humidity"] for m in measurements) / len(measurements)

    result = {
        "device_id": reading.device_id,
        "samples": len(measurements),
        "average_temperature": round(avg_temperature, 2),
        "average_humidity": round(avg_humidity, 2),
    }

    print("Medición recibida:", measurement)
    print("Procesamiento Edge:", result)

    # Enviar promedios al backend sin bloquear la respuesta al ESP32.
    # Un fallo aquí no impide que el Edge responda correctamente al dispositivo.
    send_averages_to_backend(result)

    return result

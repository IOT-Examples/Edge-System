from pydantic import BaseModel, Field
from fastapi import FastAPI
from collections import deque
from datetime import datetime, timezone

app = FastAPI(title="IoT Edge System")

# Conserva las últimas 5 mediciones en memoria
measurements = deque(maxlen=5)


class SensorReading(BaseModel):
    device_id: str
    temperature: float = Field(ge=-40, le=80)
    humidity: float = Field(ge=0, le=100)


@app.get("/health")
def health():
    return {"status": "ok", "component": "edge"}


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

    return result

# IoT Edge System

Servicio Edge desarrollado con **Python + FastAPI** que recibe, valida y procesa mediciones de temperatura y humedad enviadas por un dispositivo ESP32 (simulado en Wokwi o real), y reenvía los promedios calculados a un backend IoT (Spring Boot).

## Estructura del proyecto

```
iot-project/
└── edge/
    ├── .env.example
    ├── .gitignore
    ├── Dockerfile
    ├── docker-compose.yml
    ├── main.py
    ├── requirements.txt
    ├── requirements-test.txt
    ├── README.md
    └── tests/
        └── test_main.py
```

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Comprueba que el servicio está activo |
| `POST` | `/measurements` | Recibe una medición JSON, la valida, calcula promedios de las últimas 5 muestras, los envía al backend y devuelve el resultado al ESP32 |

Ejemplo de cuerpo de petición (desde el ESP32):
```json
{
  "device_id": "esp32_001",
  "temperature": 25.6,
  "humidity": 63.2
}
```

Ejemplo de respuesta al ESP32:
```json
{
  "device_id": "esp32_001",
  "samples": 1,
  "average_temperature": 25.6,
  "average_humidity": 63.2
}
```

## Flujo de datos

```
ESP32 + DHT22
    │  HTTP POST /measurements (JSON)
    ▼
Edge System (FastAPI en Render)
    │  1. Valida rangos (temperatura: -40..80, humedad: 0..100)
    │  2. Calcula promedios de las últimas 5 lecturas
    │  3. HTTP POST /api/v1/telemetry/averages → Backend Spring Boot
    │  4. Responde al ESP32 con los promedios (independiente del backend)
    ▼
Backend IoT (Spring Boot)
```

## Variables de entorno

Configurar en Render (o en `.env` para desarrollo local, basado en `.env.example`):

| Variable | Obligatoria | Valor por defecto | Descripción |
|----------|-------------|-------------------|-------------|
| `BACKEND_BASE_URL` | No | `""` | URL base del backend IoT, sin barra final. Ej: `https://back-example-ocx9.onrender.com` |
| `BACKEND_AVERAGES_PATH` | No | `/api/v1/telemetry/averages` | Ruta del endpoint que recibe los promedios |
| `BACKEND_API_KEY` | No | `""` | API key opcional si el backend requiere autenticación. Se envía en cabecera `X-API-Key` |
| `BACKEND_TIMEOUT` | No | `5.0` | Timeout en segundos para peticiones al backend |

**Importante:** no codificar secretos en el código fuente ni subirlos al repositorio. Usar `.env.example` como plantilla y nunca subir `.env` con valores reales.

## Ejecución local

### Con Docker Compose (recomendado)

```bash
cd iot-project/edge
cp .env.example .env   # editar .env con tus valores si es necesario
docker-compose up --build
```

### Con Python directamente

```bash
cd iot-project/edge
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

La documentación interactiva queda en `http://localhost:8000/docs`.

## Pruebas automatizadas

Instalar dependencias de prueba:

```bash
cd iot-project/edge
python -m pip install -r requirements-test.txt
```

Ejecutar todas las pruebas:

```bash
cd iot-project/edge
python -m pytest tests/ -v
```

Las pruebas cubren:

1. `GET /health` responde correctamente.
2. Recepción de medición válida del ESP32.
3. Cálculo correcto de promedios con varias mediciones.
4. Rechazo de temperaturas y humedades fuera de rango (código 422).
5. Envío de promedios al backend con `httpx` (mockeado).
6. Envío con `API key` en cabecera `X-API-Key`.
7. Registro de errores cuando el backend responde HTTP 500.
8. Registro de errores ante `TimeoutException`.
9. Registro de errores ante `ConnectError`.
10. El Edge responde `200` al ESP32 aunque el backend falle o devuelva error.
11. Si no hay `BACKEND_BASE_URL` configurada, se omite el envío sin error.

## Subir a GitHub

1. Crea un repositorio vacío en GitHub (sin inicializar con README).
2. Desde la carpeta `edge`:

```bash
git init
git add .
git commit -m "feat: Edge FastAPI con envío de promedios al backend IoT"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

## Despliegue en Render

### Como Web Service con Docker

1. Entra en [Render](https://render.com/) y crea una cuenta.
2. Pulsa **New +** → **Web Service**.
3. Conecta tu cuenta de GitHub y selecciona el repositorio.
4. Render detectará el `Dockerfile` automáticamente.
5. Configura:
   - **Runtime**: Docker
   - **Port**: `8000`
6. En la sección **Environment Variables**, añade:
   - `BACKEND_BASE_URL` = `https://back-example-ocx9.onrender.com`
   - `BACKEND_AVERAGES_PATH` = `/api/v1/telemetry/averages`
   - `BACKEND_API_KEY` = (opcional, si el backend lo requiere)
   - `BACKEND_TIMEOUT` = `5.0`
7. Pulsa **Create Web Service**.

Render construirá la imagen y desplegará el servicio. Tendrás una URL pública tipo:
`https://edge-system-4t3f.onrender.com`

### Sin Docker (buildpack de Python)

Selecciona **Runtime: Python** y comando de inicio:

```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Render inyecta automáticamente `$PORT`.

## Ejemplo de logs esperados

Cuando el Edge recibe una medición y envía los promedios al backend con éxito:

```
INFO:     Started server process [1234]
INFO:     Uvicorn running on http://0.0.0.0:8000
Medición recibida: {'device_id': 'esp32_001', 'temperature': 25.6, 'humidity': 63.2, 'received_at': '2026-10-15T...Z'}
Procesamiento Edge: {'device_id': 'esp32_001', 'samples': 1, 'average_temperature': 25.6, 'average_humidity': 63.2}
INFO: Promedios enviados al backend correctamente (status=200, device_id=esp32_001)
```

Cuando el backend responde con error (el Edge sigue respondiendo al ESP32):

```
Medición recibida: {...}
Procesamiento Edge: {...}
ERROR: Backend respondió con error (status=500, url=https://back-example-ocx9.onrender.com/api/v1/telemetry/averages)
```

Cuando hay un timeout:

```
ERROR: Timeout al enviar promedios al backend (url=https://back-example-ocx9.onrender.com/api/v1/telemetry/averages). No se puede confirmar si el backend guardó el registro.
```

## Próximos pasos

1. Conectar la ESP32 simulada en Wokwi para que envíe `POST /measurements` al Edge en Render.
2. Confirmar el contrato exacto del endpoint del backend Spring Boot (ruta, campos, autenticación).
3. Implementar el backend de microservicios para persistir los datos.
4. Añadir autenticación y validación de origen de las peticiones al Edge.

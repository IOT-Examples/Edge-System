# IoT Edge System

Servicio Edge desarrollado con **Python + FastAPI** que recibe, valida y procesa mediciones de temperatura y humedad enviadas por un dispositivo ESP32 (simulado en Wokwi o real).

## Estructura del proyecto

```
iot-project/
└── edge/
    ├── .gitignore
    ├── Dockerfile
    ├── docker-compose.yml
    ├── main.py
    ├── requirements.txt
    └── README.md
```

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Comprueba que el servicio está activo |
| `POST` | `/measurements` | Recibe una medición JSON, la valida y devuelve promedios de las últimas 5 muestras |

Ejemplo de cuerpo de petición:
```json
{
  "device_id": "esp32_001",
  "temperature": 25.6,
  "humidity": 63.2
}
```

## Ejecución local

### Con Docker Compose (recomendado)

```bash
cd iot-project/edge
docker-compose up --build
```

El servicio quedará disponible en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.

### Con Python directamente

```bash
cd iot-project/edge
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## Subir a GitHub

1. Crea un repositorio vacío en GitHub (sin inicializar con README para evitar conflictos).
2. Desde la carpeta `edge`:

```bash
git init
git add .
git commit -m "feat: servicio Edge IoT con FastAPI"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

## Despliegue en Render

Render admite despliegue desde un repositorio de GitHub usando el `Dockerfile` incluido.

### Opción A: Desplegar como Web Service con Docker

1. Entra en [Render](https://render.com/) y crea una cuenta.
2. Pulsa **New +** → **Web Service**.
3. Conecta tu cuenta de GitHub y selecciona el repositorio de este proyecto.
4. Render detectará automáticamente el `Dockerfile`.
5. Configura:
   - **Runtime**: Docker
   - **Port**: `8000` (puerto interno expuesto por el contenedor)
6. Pulsa **Create Web Service**.

Render construirá la imagen y desplegará el servicio. Una vez listo, tendrás una URL pública tipo:
`https://tu-servicio.onrender.com`

### Opción B: Desplegar sin Docker (buildpack de Python)

Si prefieres no usar Docker, en Render selecciona **Runtime: Python** y configura el comando de inicio:

```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Render inyecta automáticamente la variable de entorno `$PORT`.

### Variables de entorno (opcional)

Puedes añadir variables en el panel de Render si en el futuro necesitas configuración externa (por ejemplo, la URL del backend de microservicios).

## Próximos pasos

1. Conectar la ESP32 simulada en Wokwi para que envíe `POST /measurements`.
2. Implementar el backend de microservicios para persistir los datos.
3. Añadir autenticación y validación de origen de las peticiones.

# Imagen de despliegue: FastAPI sirve la API y el frontend estático.
# Python 3.12 porque numpy 2.2, scipy 1.15, pandas 2.2 y scikit-learn 1.6
# publican wheels cp312. En 3.13+ pip compila desde fuente y el build muere.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Las dependencias van en su propia capa para no reinstalarlas en cada push.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY data ./data

WORKDIR /app/backend

EXPOSE 8000

# Railway inyecta $PORT y rutea a esa puerta. Sin --host 0.0.0.0 uvicorn
# escucha solo en loopback y el proxy responde "Application failed to respond".
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

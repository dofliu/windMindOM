# ── windMindOM Backend Dockerfile ──
# FastAPI backend + 5 modules（M1：僅 monitoring 有實質內容）
# WMOM-20260503-01：repo baseline 整理後，monitoring 已搬到 modules/monitoring/
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (caching layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entry point + 5 modules + shared
COPY run.py .
COPY modules/ modules/
COPY shared/ shared/

# Default environment
ENV BACKEND_PORT=8100
ENV BACKEND_HOST=0.0.0.0
ENV MODBUS_PORT=5020

EXPOSE 8100 5020

CMD ["python", "run.py"]

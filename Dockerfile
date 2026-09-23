# ── windMindOM Backend Dockerfile ──
# FastAPI backend + 5 modules（M1：僅 monitoring 有實質內容）
# WMOM-20260503-01：repo baseline 整理後，monitoring 已搬到 modules/monitoring/
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (caching layer)
COPY requirements.txt .
# WMOM-20260716-06（DEC-20260716-02）：requirements.txt 的 sentence-transformers 會自動帶入
# torch，linux 環境下 pip 預設解析成 CUDA 版本（含整批 nvidia-cu13* 函式庫，本容器無 GPU 純浪費）。
# 部署容器不需要 GPU，先裝 CPU-only wheel 讓後續安裝時該依賴已被滿足，不會再拉 CUDA 版本。
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
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

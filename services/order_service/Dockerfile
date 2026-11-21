FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser
COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser . /app/services/order_service

USER appuser
ENV PYTHONPATH=/app
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health')"]

CMD ["uvicorn", "services.order_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
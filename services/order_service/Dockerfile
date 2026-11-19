# Multi-stage Dockerfile cho Order/Cart Service (Port 8002)
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY . /app/services/order_service

ENV PYTHONPATH=/app
EXPOSE 8002

CMD ["uvicorn", "services.order_service.main:app", "--host", "0.0.0.0", "--port", "8002"]

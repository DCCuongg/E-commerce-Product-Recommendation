# Multi-stage Dockerfile cho FaaS Event Collector (Port 7071)
# Build từ thư mục gốc dự án: docker build -f azure_functions/Dockerfile -t ecommerce-faas:latest .
FROM python:3.11-slim AS builder

WORKDIR /build
COPY azure_functions/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY azure_functions /app/azure_functions

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 7071

CMD ["uvicorn", "azure_functions.LogInteractionFunction:create_standalone_faas_app", "--factory", "--host", "0.0.0.0", "--port", "7071"]
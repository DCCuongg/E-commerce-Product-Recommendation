# Multi-stage Dockerfile cho Auth Service (Port 8001)
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY . /app/services/auth_service

ENV PYTHONPATH=/app
EXPOSE 8001

CMD ["uvicorn", "services.auth_service.main:app", "--host", "0.0.0.0", "--port", "8001"]

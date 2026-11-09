# Multi-stage Dockerfile cho Recommender Service (Port 8003)
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY . /app/services/recommender_service

ENV PYTHONPATH=/app
EXPOSE 8003

CMD ["uvicorn", "services.recommender_service.main:app", "--host", "0.0.0.0", "--port", "8003"]

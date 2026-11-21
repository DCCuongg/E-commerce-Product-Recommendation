# Multi-stage Dockerfile cho Recommender Service (Port 8003)
FROM python:3.11-slim AS builder

WORKDIR /build
COPY services/recommender_service/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY services/recommender_service /app/services/recommender_service
COPY models /app/models
COPY scripts/sql/seed_products.sql /app/scripts/sql/seed_products.sql

ENV PYTHONPATH=/app
EXPOSE 8003

CMD ["uvicorn", "services.recommender_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends nodejs ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=frontend /build/node_modules/typescript ./node_modules/typescript
COPY backend/ backend/
COPY scripts/parse-tcgdex.mjs scripts/
COPY config/ config/
COPY --from=frontend /build/dist frontend/dist/
RUN mkdir -p data storage && useradd --uid 10001 --create-home carto && chown -R carto:carto /app
USER carto
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

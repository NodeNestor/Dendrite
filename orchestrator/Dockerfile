FROM node:22-slim AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "httpx>=0.27" \
    "pydantic>=2.9" \
    "pydantic-settings>=2.5" \
    "trafilatura>=1.12" \
    "mcp>=1.0" \
    "websockets>=13"

COPY src/ ./src/
COPY --from=frontend-build /build/dist ./static/

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]

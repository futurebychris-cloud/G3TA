FROM node:22-alpine AS frontend-build

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

ARG VITE_AMAP_KEY=""
ARG VITE_AMAP_SECURITY_CODE=""
ENV VITE_AMAP_KEY=${VITE_AMAP_KEY}
ENV VITE_AMAP_SECURITY_CODE=${VITE_AMAP_SECURITY_CODE}
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOOKING_AUTOMATION_ENABLED=1

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && python -m playwright install --with-deps chromium

COPY backend/ /app/backend/
COPY --from=frontend-build /src/frontend/dist/ /app/frontend/dist/

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/api/pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY apps/api/ ./
COPY src ./src
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["python", "-m", "app.server"]

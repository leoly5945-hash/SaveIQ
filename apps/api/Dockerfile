FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/api/pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY apps/api/ ./
COPY src ./src
ENV PYTHONPATH=/app

# Don't run the process as root — an RCE in any dependency shouldn't hand the
# attacker root inside the container for free.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["python", "-m", "app.server"]

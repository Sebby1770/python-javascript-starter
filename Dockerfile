FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md openapi.yaml ./
COPY src ./src
COPY web ./web
COPY data ./data

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "taskpulse.server"]
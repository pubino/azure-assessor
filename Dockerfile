FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .[dev]

COPY azure_assessor/ azure_assessor/
COPY tests/ tests/

CMD ["pytest", "-v", "--tb=short", "--co", "-q"]

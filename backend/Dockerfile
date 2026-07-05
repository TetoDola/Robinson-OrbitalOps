FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY pyproject.toml .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

COPY . .

CMD ["python", "-m", "app.services.bootstrap"]

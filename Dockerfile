FROM python:3.11-slim

LABEL maintainer="Felix Brillant"
LABEL project="Stockout Decision Intelligence Platform"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY . .

CMD ["python", "-m", "pytest", "-q"]

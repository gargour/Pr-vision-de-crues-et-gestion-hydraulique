ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
# Dépendances d'abord : cette couche est mise en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code et configuration (les données ne sont PAS dans l'image)
COPY config.yaml pytest.ini ./
COPY configs ./configs
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts

CMD ["python", "-m", "src.pipeline"]
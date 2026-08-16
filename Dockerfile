FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       aria2 \
       ffmpeg \
       gcc \
       git \
       jq \
       libcurl4-openssl-dev \
       mediainfo \
       python3-dev \
       pv \
       wget \
    && rm -rf /var/lib/apt/lists/*

COPY xxx-main/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY xxx-main/ .
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8080
CMD ["/app/docker-entrypoint.sh"]

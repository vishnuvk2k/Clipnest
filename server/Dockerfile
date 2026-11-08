# Clipnest Online: the public website version of Clipnest.
# Build from the project folder:  docker build -f server/Dockerfile -t clipnest-online .
FROM python:3.12-slim

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install "yt-dlp[default]" \
 && useradd --create-home clipnest

WORKDIR /app
# Only what the website needs: no desktop (Qt) code.
COPY clipnest/__init__.py clipnest/jobs.py clipnest/
COPY clipnest/web clipnest/web
COPY server server

USER clipnest
# yt-dlp updates at start go to the user's folder; use those first.
ENV PATH="/home/clipnest/.local/bin:${PATH}"
EXPOSE 8080
# Update yt-dlp on every start, so the website keeps working when sites change.
CMD ["sh", "-c", "pip install --user --upgrade --quiet 'yt-dlp[default]' >/dev/null 2>&1; exec python -m server.main"]

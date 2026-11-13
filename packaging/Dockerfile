FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/jk-venv/bin:${PATH}" \
    LIBGL_ALWAYS_SOFTWARE=1

# Match the packaged Ubuntu 24.04 x86-64 engines. The manager selects the
# engine's surfaceless EGL backend and separately gives bot clients Xvfb.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates python3 python3-venv \
      libgtk-3-0t64 libopenal1 libgl1 libegl1 libgl1-mesa-dri libegl-mesa0 \
      libcurl4t64 libsndio7.0 libssl3t64 xvfb xauth \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/jk-venv

COPY web_gateway/requirements-lock.txt /tmp/requirements-lock.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-lock.txt

WORKDIR /app
COPY . /app/
RUN chmod 755 /app/bin/linux-x86_64/openjkdf2 /app/bin/bots-linux-x86_64/jk-bot-client \
    && python -m web_gateway.fetch_client --destination /opt/jk-web
COPY packaging/container_runtime.py /usr/local/bin/jk-container-runtime.py

# Compose seeds this writable application volume from the image, allowing the
# existing verified in-place updater to retain its normal lock/rollback behavior.
VOLUME ["/app"]
EXPOSE 8766/tcp 8787/tcp 3500/udp
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=3).read(1)"]
ENTRYPOINT ["python", "/usr/local/bin/jk-container-runtime.py"]

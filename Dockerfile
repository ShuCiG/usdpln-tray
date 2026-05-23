FROM python:3.13-slim

WORKDIR /app

# Install dependencies. requirements.txt uses sys_platform markers so the
# Windows-only tray/chart packages are skipped automatically on Linux.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only the files needed for headless mode. chart.py and PIL assets are
# Windows-only and not used in the container.
COPY tray.py notify.py ./

# Override the default paths so the SQLite DB and config sit on mounted
# volumes instead of inside the image.
ENV USDPLN_DB_PATH=/data/rates.db \
    USDPLN_CONFIG_PATH=/config/config.json \
    PYTHONUNBUFFERED=1

# /data   - persisted SQLite database (rates + alerts)
# /config - mount your config.json here, typically read-only
VOLUME ["/data", "/config"]

CMD ["python", "tray.py", "--headless"]

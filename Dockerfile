FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 1000 pppoe \
    && useradd --uid 1000 --gid 1000 --no-create-home pppoe \
    && install -d -o pppoe -g pppoe -m 0700 /app/instance

COPY app.py ip_analyzer.py live_monitor.py pppoe_monitor.py router_client.py ./
COPY templates/ ./templates/
COPY static/ ./static/

USER 1000:1000
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:5000/login', timeout=3).close()"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--access-logfile", "-", "app:app"]

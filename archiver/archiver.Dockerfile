FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY archiver.py .

USER 1000:1000

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os; os.kill(1, 0)" || exit 1

ENTRYPOINT ["python", "archiver.py", "--config", "/config.yml"]

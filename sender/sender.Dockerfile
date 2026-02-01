FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sender.py .

RUN mkdir /data && chown 1000:1000 /data
RUN mkdir /watch && chown 1000:1000 /watch

VOLUME [ "/data" ]

ENV PYTHONUNBUFFERED=1

USER 1000:1000

ENTRYPOINT ["python", "sender.py", "--config", "/config.yml"]

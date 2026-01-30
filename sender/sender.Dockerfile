FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sender.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

RUN mkdir /data && chown 1000:1000 /data
RUN mkdir /watch && chown 1000:1000 /watch

VOLUME [ "/data" ]

ENV PYTHONUNBUFFERED=1

USER 1000:1000

ENTRYPOINT ["/app/entrypoint.sh"]

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sender.py .

# Use unbuffered output so logs appear in real-time
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "sender.py"]

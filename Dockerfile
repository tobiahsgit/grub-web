FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install flask flask-cors yt-dlp spotdl

WORKDIR /app
COPY . .

ENV PORT=8080
CMD ["python", "server.py"]

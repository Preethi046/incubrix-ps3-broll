FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY broll ./broll
RUN useradd --create-home app && mkdir -p /data && chown app:app /data
USER app
ENV BROLL_DATA_DIR=/data BROLL_DATABASE=/data/jobs.sqlite3
EXPOSE 8000
CMD ["uvicorn", "broll.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

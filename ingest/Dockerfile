FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sturgeon_ingest ./sturgeon_ingest

ENTRYPOINT ["python", "-m", "sturgeon_ingest"]

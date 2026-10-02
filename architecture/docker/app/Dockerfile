# Build context: repository root (see compose.yaml). The code itself is mounted
# at /app at runtime, so only the dependencies are baked into the image.
FROM python:3.11-slim

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
CMD ["python", "main.py", "--help"]

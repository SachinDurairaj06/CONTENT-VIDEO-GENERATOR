# Build stage
FROM python:3.11-slim

# Install system dependencies (FFmpeg is required for the pipeline)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install flask gunicorn boto3 python-dotenv

# Copy the rest of the application
COPY . .

# Expose the port Flask/Gunicorn will run on
EXPOSE 5000

# Run with Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "600", "backend_server:app"]

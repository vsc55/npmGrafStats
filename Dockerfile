# Stage 1: Build environment
FROM python:3.14-slim AS builder

LABEL maintainer="npmgrafstats@cerebelum.net"

# Install necessary packages for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY ./root/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 2: Runtime environment
FROM python:3.14-slim

# Python environment variables
ENV PYTHONUNBUFFERED=1

# Install curl in the final image
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# create log and geolite directories
RUN mkdir -p /logs /geolite /app

# Copy installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

# Copy application files
COPY ./root /app
RUN chmod +x /app/main.py

WORKDIR /app
ENTRYPOINT ["python3", "main.py"]
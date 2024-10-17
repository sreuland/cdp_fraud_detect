# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install system dependencies, including 'patch' for lmdb
RUN apt-get update && apt-get install -y \
    build-essential \
    liblmdb-dev \
    patch \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file
COPY ../requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the app code
COPY . /app

# Expose port 8080
EXPOSE 8080

# Command to run the fetch and store script
CMD ["python", "fetch_store_unsafe_accts/fetch_and_store.py"]

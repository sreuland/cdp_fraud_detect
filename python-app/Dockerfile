# Use an official Python image.
FROM python:3.9-slim

# Set working directory inside the container.
WORKDIR /app

# Copy the requirements file to the working directory.
COPY ../requirements.txt /app/requirements.txt

# Install Python dependencies.
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the application code into the container.
COPY . /app

# Expose port 8000 for the FastAPI app.
EXPOSE 8000

# Set the command to run the FastAPI app with uvicorn.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

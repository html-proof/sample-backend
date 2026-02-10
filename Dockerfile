# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for yt-dlp (ffmpeg is highly recommended for audio extraction)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose is handled by many platforms via PORT env, removing hardcoded hint
# Command to run the application using python main.py for custom port logic
# Command to run the application using python main.py for custom port logic
CMD ["python", "main.py"]

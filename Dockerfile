# Use a lightweight Python base image
FROM python:3.10-slim

# 1. Install system dependencies (FFmpeg is critical here)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. Set working directory
WORKDIR /app

# 3. Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of the application code
COPY . .

# 5. Expose the port (Render usually uses 10000 or 8080 internally)
EXPOSE 10000

# 6. Command to run the server using Gunicorn
# "-w 4" means 4 worker processes (handles multiple connections better)
# "-b 0.0.0.0:10000" binds to all interfaces on port 10000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:10000", "--timeout", "120", "server:app"]
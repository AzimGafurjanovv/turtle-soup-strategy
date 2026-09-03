FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment configuration
ENV PORT=8080
EXPOSE 8080

# Start command
CMD ["python", "main.py", "--web"]

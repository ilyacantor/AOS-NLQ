FROM python:3.11-slim

# Install Node.js 20 for frontend build
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node dependencies
COPY package.json package-lock.json ./
RUN npm ci --include=dev

# Application source
COPY . .

# Build frontend — produces dist/ in the same image used at runtime
RUN npm run build && \
    test -f dist/index.html || (echo "FATAL: dist/index.html missing" && exit 1)

EXPOSE 10000

CMD ["uvicorn", "src.nlq.main:app", "--host", "0.0.0.0", "--port", "10000"]

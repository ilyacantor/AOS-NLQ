#!/bin/bash
# Production start script - builds React and starts FastAPI on port 5000

cd "$(dirname "$0")"

echo "Building Tailwind CSS..."
npx @tailwindcss/cli -i src/index.css -o src/index.built.css --content "src/**/*.{ts,tsx}" --minify

echo "Building React frontend..."
npm run build

echo "Starting FastAPI server on port 5000..."
exec uvicorn src.nlq.main:app --host 0.0.0.0 --port 5000

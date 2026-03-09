#!/usr/bin/env bash
set -euo pipefail

echo "=== NLQ Build Script ==="
echo "Python: $(python --version 2>&1)"
echo "Node: $(node --version 2>&1 || echo 'NOT FOUND')"
echo "npm: $(npm --version 2>&1 || echo 'NOT FOUND')"
echo "CWD: $(pwd)"

echo "--- Step 1: pip install ---"
pip install -r requirements.txt

echo "--- Step 2: npm ci ---"
npm ci --include=dev

echo "--- Step 3: npm run build (vite) ---"
npm run build

echo "--- Step 4: Verify dist/ ---"
if [ -f dist/index.html ]; then
    echo "SUCCESS: dist/index.html exists"
    ls -la dist/
else
    echo "FATAL: dist/index.html does NOT exist after build"
    echo "Contents of current directory:"
    ls -la
    exit 1
fi

echo "=== Build complete ==="

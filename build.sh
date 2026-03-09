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
if [ ! -f dist/index.html ]; then
    echo "FATAL: dist/index.html does NOT exist after build"
    ls -la
    exit 1
fi
echo "SUCCESS: dist/index.html exists"

# Render's Python runtime strips Node artifacts (dist/, node_modules/)
# between build and runtime phases. Copy dist/ into the Python source
# tree so it survives into the runtime environment.
echo "--- Step 5: Copy dist/ into Python source tree ---"
rm -rf src/nlq/_dist
cp -r dist/ src/nlq/_dist/
echo "Copied dist/ -> src/nlq/_dist/"
ls -la src/nlq/_dist/

echo "=== Build complete ==="

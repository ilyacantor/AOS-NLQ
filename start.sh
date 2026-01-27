#!/bin/bash
cd "$(dirname "$0")"
exec npx vite --host 0.0.0.0 --port 5000

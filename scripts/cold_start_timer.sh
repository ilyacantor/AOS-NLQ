#!/usr/bin/env bash
# Cold-start timing diagnostic for NLQ-to-DCL connectivity.
# Usage: ./scripts/cold_start_timer.sh
#
# Restarts NLQ via pm2, then polls /api/v1/pipeline/status every 2s
# until dcl_connected=true with metrics > 0. Reports elapsed time.

set -euo pipefail

NLQ_URL="http://localhost:8005"
POLL_INTERVAL=2
TIMEOUT=180  # 3 minutes max

echo "=== NLQ Cold-Start Timing Diagnostic ==="
echo ""

# 1. Check DCL is running and ready first
echo "[DCL pre-check] Checking DCL health..."
DCL_HEALTH=$(curl -s http://localhost:8004/api/health 2>/dev/null || echo '{"error":"unreachable"}')
DCL_PHASE=$(echo "$DCL_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('phase','unknown'))" 2>/dev/null || echo "unknown")
echo "[DCL pre-check] DCL phase: $DCL_PHASE"
if [ "$DCL_PHASE" != "ready" ]; then
    echo "[DCL pre-check] WARNING: DCL is not in 'ready' phase. Results will include DCL warm-up time."
fi
echo ""

# 2. Restart NLQ
echo "[restart] Stopping NLQ..."
pm2 stop nlq-backend 2>/dev/null || true
sleep 1

echo "[restart] Starting NLQ..."
START_TIME=$(date +%s%3N)  # milliseconds
pm2 start nlq-backend 2>/dev/null
echo "[restart] NLQ started at $(date '+%H:%M:%S')"
echo ""

# 3. Wait for NLQ to accept connections
echo "[wait] Waiting for NLQ to accept HTTP..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" "$NLQ_URL/api/v1/health" 2>/dev/null | grep -q "200"; then
        HTTP_UP_TIME=$(date +%s%3N)
        ELAPSED_HTTP=$(( (HTTP_UP_TIME - START_TIME) / 1000 ))
        echo "[wait] NLQ accepting HTTP after ${ELAPSED_HTTP}s"
        break
    fi
    sleep 1
done
echo ""

# 4. Poll pipeline/status until connected
echo "[poll] Polling /api/v1/pipeline/status every ${POLL_INTERVAL}s (timeout ${TIMEOUT}s)..."
echo ""
printf "%-8s %-12s %-10s %-8s %-18s\n" "Time(s)" "Connected" "Metrics" "Mode" "CatalogSource"
printf "%-8s %-12s %-10s %-8s %-18s\n" "------" "---------" "-------" "----" "-------------"

CONNECTED=false
while true; do
    NOW=$(date +%s%3N)
    ELAPSED=$(( (NOW - START_TIME) / 1000 ))

    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo ""
        echo "[TIMEOUT] Failed to connect within ${TIMEOUT}s"
        exit 1
    fi

    RESPONSE=$(curl -s "$NLQ_URL/api/v1/pipeline/status" 2>/dev/null || echo '{}')

    DCL_CONN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dcl_connected', False))" 2>/dev/null || echo "False")
    METRICS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metric_count', 0))" 2>/dev/null || echo "0")
    MODE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dcl_mode', 'None'))" 2>/dev/null || echo "None")
    SOURCE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('catalog_source', 'None'))" 2>/dev/null || echo "None")

    printf "%-8s %-12s %-10s %-8s %-18s\n" "${ELAPSED}s" "$DCL_CONN" "$METRICS" "$MODE" "$SOURCE"

    if [ "$DCL_CONN" = "True" ] && [ "$METRICS" -gt 0 ] 2>/dev/null; then
        echo ""
        FINAL_TIME=$(date +%s%3N)
        TOTAL_SECONDS=$(( (FINAL_TIME - START_TIME) / 1000 ))
        echo "=== CONNECTED in ${TOTAL_SECONDS}s ==="
        echo "  Metrics: $METRICS"
        echo "  Mode: $MODE"
        echo "  Source: $SOURCE"

        if [ "$TOTAL_SECONDS" -le 20 ]; then
            echo "  Result: PASS (<= 20s target)"
        else
            echo "  Result: FAIL (> 20s target)"
        fi
        exit 0
    fi

    sleep "$POLL_INTERVAL"
done

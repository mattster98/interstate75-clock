#!/bin/bash
# Usage: push.sh [local_file] [remote_name]
# Default remote name is main.py. Pushes secrets.py + file then soft-resets the board.
DIR="$(cd "$(dirname "$0")" && pwd)"
PASSWD=$(python3 -c "import sys; sys.path.insert(0,'$DIR'); from secrets import WEBREPL_PASSWD; print(WEBREPL_PASSWD)")
HOST="192.168.10.192"

# Retry until webrepl is up (board can take 20-40s to connect WiFi + start webrepl)
MAX=12; WAIT=5
for i in $(seq 1 $MAX); do
    echo "Attempt $i/$MAX: pushing secrets.py..."
    python3 ~/webrepl_cli.py -p "$PASSWD" "$DIR/secrets.py" "$HOST:/secrets.py" && break
    [ $i -lt $MAX ] && echo "  webrepl not ready, retrying in ${WAIT}s..." && sleep $WAIT
done || { echo "ERROR: board not reachable after $((MAX * WAIT))s"; exit 1; }

echo "Pushing ${1:-clock.py}..."
python3 ~/webrepl_cli.py -p "$PASSWD" "${1:-$DIR/clock.py}" "$HOST:/${2:-main.py}" && \
python3 "$DIR/webrepl_reset.py"

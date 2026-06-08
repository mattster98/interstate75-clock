#!/bin/bash
# Usage: push.sh [local_file] [remote_name]
# Default remote name is main.py. Pushes secrets.py + file then soft-resets the board.
DIR="$(cd "$(dirname "$0")" && pwd)"
PASSWD=$(python3 -c "import sys; sys.path.insert(0,'$DIR'); from secrets import WEBREPL_PASSWD; print(WEBREPL_PASSWD)")
python3 ~/webrepl_cli.py -p "$PASSWD" "$DIR/secrets.py" "192.168.10.192:/secrets.py" && \
python3 ~/webrepl_cli.py -p "$PASSWD" "${1:-$DIR/clock.py}" "192.168.10.192:/${2:-main.py}" && \
python3 "$DIR/webrepl_reset.py"

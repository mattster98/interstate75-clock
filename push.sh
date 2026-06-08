#!/bin/bash
# Usage: push.sh [local_file] [remote_name]
# Default remote name is main.py. Pushes file then soft-resets the board.
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 ~/webrepl_cli.py -p 0x4d9l1q "${1:-$DIR/clock.py}" "192.168.10.192:/${2:-main.py}" && \
python3 "$DIR/webrepl_reset.py"

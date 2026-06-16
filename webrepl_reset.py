#!/usr/bin/env python3
"""Hard-reset a MicroPython board via WebREPL using machine.reset()."""
import os
import sys
import socket
import time

sys.path.insert(0, '/home/matts')
from webrepl_cli import websocket, client_handshake, login, WEBREPL_FRAME_TXT

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from secrets import WEBREPL_PASSWD

HOST   = "192.168.10.82"
PORT   = 8266
PASSWD = WEBREPL_PASSWD

s = socket.socket()
s.connect(socket.getaddrinfo(HOST, PORT)[0][4])
client_handshake(s)
ws = websocket(s)
login(ws, PASSWD)

# Enter raw REPL (Ctrl+A), then send machine.reset() and execute (Ctrl+D).
# This works even when asyncio.run() is active, unlike a plain Ctrl+D soft reset.
ws.write(b'\x01', WEBREPL_FRAME_TXT)   # Ctrl+A: raw REPL mode
time.sleep(0.2)
ws.write(b'import machine; machine.reset()\r\n', WEBREPL_FRAME_TXT)
time.sleep(0.1)
ws.write(b'\x04', WEBREPL_FRAME_TXT)   # Ctrl+D: execute
time.sleep(0.5)
s.close()
print("Board reset.")

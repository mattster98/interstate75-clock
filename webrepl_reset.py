#!/usr/bin/env python3
"""Send a soft reset (Ctrl+D) to a MicroPython board via WebREPL."""
import os
import sys
import socket
import time

# Reuse the websocket, handshake, and login from webrepl_cli
sys.path.insert(0, '/home/matts')
from webrepl_cli import websocket, client_handshake, login, WEBREPL_FRAME_TXT

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from secrets import WEBREPL_PASSWD

HOST   = "192.168.10.198"
PORT   = 8266
PASSWD = WEBREPL_PASSWD

s = socket.socket()
ai = socket.getaddrinfo(HOST, PORT)
s.connect(ai[0][4])
client_handshake(s)
ws = websocket(s)
login(ws, PASSWD)

# Ctrl+D = soft reset in MicroPython REPL
ws.write(b'\x04', WEBREPL_FRAME_TXT)
time.sleep(0.5)
s.close()
print("Board reset.")

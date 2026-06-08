#!/usr/bin/env python3
"""Send a soft reset (Ctrl+D) to a MicroPython board via WebREPL."""
import sys
import socket
import time

# Reuse the websocket, handshake, and login from webrepl_cli
sys.path.insert(0, '/home/matts')
from webrepl_cli import websocket, client_handshake, login, WEBREPL_FRAME_TXT

HOST   = "192.168.10.192"
PORT   = 8266
PASSWD = "0x4d9l1q"

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

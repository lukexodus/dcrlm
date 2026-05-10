#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Member 4 — Client Developer
# Worker Client: connects to Lock Manager and requests exclusive resource access.

import socket
import threading
import sys
import argparse
from utils import LamportClock, send_json, recv_json, get_local_ip
from config import *

def resolve_lock_server(ns_host, ns_port):
    """
    Resolve the Lock Server address from the Naming Server.
    """

    ns_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Connect to Naming Server
        ns_sock.connect((ns_host, ns_port))

        # Build LOOKUP request
        request = f"LOOKUP {LOCK_SERVER_NAME}\n"

        # Send request
        ns_sock.sendall(request.encode("utf-8"))

        # Receive response
        response = ns_sock.recv(1024).decode("utf-8").strip()

        # Handle FOUND response
        if response.startswith("FOUND"):
            parts = response.split()

            ip = parts[1]
            port = int(parts[2])

            print(f"[WC][--] Resolved {LOCK_SERVER_NAME} -> {ip}:{port}")

            return ip, port

        # Handle NOT_FOUND response
        if response == "NOT_FOUND":
            print(f"[WC][ERROR] {LOCK_SERVER_NAME} not found.")
            sys.exit(1)

        # Unexpected response
        print(f"[WC][ERROR] Unexpected response: {response}")
        sys.exit(1)

    finally:
        # Always close socket
        ns_sock.close()

if __name__ == "__main__":

    ip, port = resolve_lock_server(
        NAMING_SERVER_HOST,
        NAMING_SERVER_PORT
    )

    print(f"Resolved Lock Server: {ip}:{port}")
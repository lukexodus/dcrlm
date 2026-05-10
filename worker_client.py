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


def send_request(sock, clock, worker_id):
    """
    Send a lock request message to the Lock Manager.
    """

    # Increment Lamport clock before sending
    timestamp = clock.send()

    # Build request message
    msg = {
        "type": "request_lock",
        "worker_id": worker_id,
        "timestamp": timestamp,
        "resource": SHARED_RESOURCE_NAME
    }

    # Send message
    send_json(sock, msg)

    print(f"[WC][{worker_id}] Sent request_lock at timestamp {timestamp}")


def send_release(sock, clock, worker_id):
    """
    Send a lock release message to the Lock Manager.
    """

    # Increment Lamport clock before sending
    timestamp = clock.send()

    # Build release message
    msg = {
        "type": "release_lock",
        "worker_id": worker_id,
        "timestamp": timestamp
    }

    # Send message
    send_json(sock, msg)

    print(f"[WC][{worker_id}] Sent release_lock at timestamp {timestamp}")

def listener_thread(sock, clock, state):
    """
    Stub listener thread.
    Receives messages from the Lock Manager and prints them.
    """

    while True:
        try:
            msg = recv_json(sock)

            if "timestamp" in msg:
                clock.receive(msg["timestamp"])

            print(f"\n[WC][RECEIVED] {msg}")

        except ConnectionError:
            print("\n[WC][ERROR] Disconnected from Lock Manager.")
            return


def input_loop(sock, clock, worker_id, state):
    """
    Stub input loop.
    Reads user commands from the terminal.
    """

    while True:
        command = input("> ").strip().lower()

        if command == "quit":
            print("Goodbye")
            sys.exit(0)

        print("TODO: handle command")


if __name__ == "__main__":

    ip, port = resolve_lock_server(
        NAMING_SERVER_HOST,
        NAMING_SERVER_PORT
    )

    print(f"Resolved Lock Server: {ip}:{port}")
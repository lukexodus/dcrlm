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
    Full listener thread for Phase 3+.
    Receives messages from the Lock Manager and updates state.
    Runs in background daemon thread.
    """

    while True:
        try:
            # Receive message from Lock Manager
            msg = recv_json(sock)

            # Update Lamport clock if message has timestamp
            if "timestamp" in msg:
                clock.receive(msg["timestamp"])

            # Acquire state lock for safe state updates
            state["state_lock"].acquire()

            try:
                # Process message based on type
                msg_type = msg.get("type", "")

                if msg_type == "lock_granted":
                    # Worker has been granted the lock
                    state["holds_lock"] = True
                    state["queue_position"] = 0
                    print(f"[WC][{state['worker_id']}] ✓ LOCK GRANTED at timestamp {clock.value()}")

                elif msg_type == "lock_released":
                    # Lock was released by another worker or timeout
                    if state["holds_lock"]:
                        state["holds_lock"] = False
                    print(f"[WC][{state['worker_id']}] ⊘ Lock released, queue updated")

                elif msg_type == "queue_update":
                    # Queue state changed
                    state["queue"] = msg.get("queue", [])
                    state["lock_holder"] = msg.get("lock_holder")

                    # Find this worker's position in queue
                    for idx, entry in enumerate(state["queue"]):
                        if entry["worker_id"] == state["worker_id"]:
                            state["queue_position"] = idx
                            break
                    else:
                        state["queue_position"] = -1  # Not in queue

                    print(f"[WC][{state['worker_id']}] Queue updated. Position: {state['queue_position']}, Holder: {state['lock_holder']}")

                elif msg_type == "error":
                    # Error from Lock Manager
                    print(f"\n[WC][ERROR] {msg.get('message', 'Unknown error')}")

                else:
                    print(f"[WC][{state['worker_id']}] Received message type '{msg_type}': {msg}")

            finally:
                # Always release state lock
                state["state_lock"].release()

        except ConnectionError:
            print(f"\n[WC][{state['worker_id']}] ERROR: Disconnected from Lock Manager")
            state["state_lock"].acquire()
            state["connected"] = False
            state["state_lock"].release()
            return

        except Exception as e:
            print(f"[WC][{state['worker_id']}] Exception in listener: {e}")
            return


def input_loop(sock, clock, worker_id, state):
    """
    Full input loop for Phase 3+.
    Reads user commands and processes them.
    Runs in main thread after connection established.
    """

    print(f"\n[WC][{worker_id}] Interactive mode. Type commands:")
    print(f"  request  - Request the lock")
    print(f"  release  - Release the lock")
    print(f"  status   - Show current state")
    print(f"  quit     - Exit")
    print()

    try:
        while True:
            # Read command from user
            try:
                command = input("> ").strip().lower()
            except EOFError:
                # Handle EOF gracefully
                print("\nGoodbye")
                sys.exit(0)

            if not command:
                continue

            # "request" command
            if command == "request":
                state["state_lock"].acquire()
                try:
                    if state["holds_lock"]:
                        print(f"[WC][{worker_id}] You already hold the lock.")
                    elif state["queue_position"] >= 0:
                        print(f"[WC][{worker_id}] You are already waiting in queue at position {state['queue_position']}")
                    else:
                        # Not holding lock and not in queue: send request
                        state["state_lock"].release()
                        send_request(sock, clock, worker_id)
                        state["state_lock"].acquire()
                finally:
                    state["state_lock"].release()

            # "release" command
            elif command == "release":
                state["state_lock"].acquire()
                try:
                    if not state["holds_lock"]:
                        print(f"[WC][{worker_id}] You do not hold the lock.")
                    else:
                        # Release the lock
                        state["state_lock"].release()
                        send_release(sock, clock, worker_id)
                        state["state_lock"].acquire()
                finally:
                    state["state_lock"].release()

            # "status" command
            elif command == "status":
                state["state_lock"].acquire()
                try:
                    print(f"\n--- Status for {worker_id} ---")
                    print(f"  Clock: {clock.value()}")
                    print(f"  Holds Lock: {state['holds_lock']}")
                    print(f"  Queue Position: {state['queue_position']}")
                    print(f"  Lock Holder: {state['lock_holder']}")
                    if state["queue"]:
                        print(f"  Queue: {[q['worker_id'] for q in state['queue']]}")
                    else:
                        print(f"  Queue: (empty)")
                    print()
                finally:
                    state["state_lock"].release()

            # "quit" command
            elif command == "quit":
                state["state_lock"].acquire()
                try:
                    if state["holds_lock"]:
                        # Release before exiting
                        state["state_lock"].release()
                        send_release(sock, clock, worker_id)
                        state["state_lock"].acquire()
                finally:
                    state["state_lock"].release()
                print("Goodbye")
                sys.exit(0)

            else:
                print(f"[WC] Unknown command: '{command}'. Try: request, release, status, quit")

    except KeyboardInterrupt:
        # Handle Ctrl+C
        print("\n[WC] Interrupted by user")
        state["state_lock"].acquire()
        try:
            if state["holds_lock"]:
                state["state_lock"].release()
                send_release(sock, clock, worker_id)
                state["state_lock"].acquire()
        finally:
            state["state_lock"].release()
        sys.exit(0)


def handle_connect_response(sock):
    """
    Handle the initial connection response from Lock Manager.
    Waits for queue_update message confirming connection.
    """

    # Set a timeout for the initial response
    sock.settimeout(SOCKET_TIMEOUT_SEC)

    try:
        # Receive response
        msg = recv_json(sock)

        # Check for error response
        if msg.get("type") == "error":
            print(f"[WC][ERROR] Connection rejected: {msg.get('message', 'Unknown error')}")
            sock.close()
            return False

        # Check for queue_update (successful connection)
        if msg.get("type") == "queue_update":
            print(f"[WC][--] Connected successfully to Lock Manager")
            # Reset timeout to None (blocking mode)
            sock.settimeout(None)
            return True

        # Unexpected response
        print(f"[WC][ERROR] Unexpected response: {msg}")
        sock.close()
        return False

    except socket.timeout:
        print(f"[WC][ERROR] Connection timeout")
        sock.close()
        return False

    except ConnectionError as e:
        print(f"[WC][ERROR] Connection error: {e}")
        sock.close()
        return False


def start_worker(worker_id, ns_host, ns_port):
    """
    Main entry point for Worker Client.
    Resolves Lock Manager, connects, sends hello, then enters interactive loop.
    """

    # Resolve Lock Manager from Naming Server
    try:
        lm_ip, lm_port = resolve_lock_server(ns_host, ns_port)
    except SystemExit:
        return

    # Create Lamport clock for this worker
    clock = LamportClock()

    # Initialize state dictionary
    state = {
        "worker_id": worker_id,
        "clock": clock,
        "holds_lock": False,
        "queue_position": -1,
        "lock_holder": None,
        "queue": [],
        "connected": False,
        "state_lock": threading.Lock()
    }

    # Connect to Lock Manager
    try:
        lm_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lm_sock.connect((lm_ip, lm_port))
        print(f"[WC][--] Connected to Lock Manager at {lm_ip}:{lm_port}")
    except Exception as e:
        print(f"[WC][ERROR] Failed to connect to Lock Manager: {e}")
        sys.exit(1)

    # Send hello message
    try:
        # Increment clock for local event
        clock.tick()

        hello_msg = {
            "type": "hello",
            "worker_id": worker_id
        }

        send_json(lm_sock, hello_msg)
        print(f"[WC][{worker_id}] Sent hello message")
    except Exception as e:
        print(f"[WC][ERROR] Failed to send hello: {e}")
        lm_sock.close()
        sys.exit(1)

    # Wait for connection response
    if not handle_connect_response(lm_sock):
        sys.exit(1)

    state["connected"] = True

    # Start listener thread as daemon
    listener = threading.Thread(
        target=listener_thread,
        args=(lm_sock, clock, state),
        daemon=True
    )
    listener.start()

    # Give listener thread time to receive initial queue_update
    threading.Event().wait(0.1)

    # Enter interactive input loop (blocks until user quits)
    try:
        input_loop(lm_sock, clock, worker_id, state)
    except KeyboardInterrupt:
        print("\n[WC] Shutting down")
        sys.exit(0)
    finally:
        lm_sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Worker Client for Distributed Cloud Resource Lock Manager"
    )

    parser.add_argument(
        "--id",
        required=True,
        help="Unique worker ID (e.g., WA, WB, WC)"
    )

    parser.add_argument(
        "--ns-host",
        default=NAMING_SERVER_HOST,
        help=f"Naming Server host (default: {NAMING_SERVER_HOST})"
    )

    parser.add_argument(
        "--ns-port",
        type=int,
        default=NAMING_SERVER_PORT,
        help=f"Naming Server port (default: {NAMING_SERVER_PORT})"
    )

    args = parser.parse_args()

    # Start the worker client
    start_worker(args.id, args.ns_host, args.ns_port)
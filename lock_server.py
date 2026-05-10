#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Member 5 — Server Developer and Integrator
# Lock Manager: enforces distributed mutual exclusion using Lamport clocks.

import socket
import threading
import time
import sys
import argparse
from utils import LamportClock, send_json, recv_json, sort_queue, build_queue_update_msg
from utils import simulate_resource_use, check_lock_timeout, get_local_ip
from config import *


# ---------------------------------------------------------------------------
# Task 2.21 helper — shared server state
# Defined here so all functions below can reference the same schema.
# Fields match Section 8 of the Shared Integration Specification exactly.
# ---------------------------------------------------------------------------

def _make_state(clock):
    """
    Build and return the shared server state dictionary.
    Every field is listed explicitly so every member knows what to expect.
    """
    return {
        "clock":           clock,             # LamportClock — one instance, all threads share it
        "lock_queue":      [],                # list of {"worker_id": str, "timestamp": int}
        "lock_holder":     None,              # str | None — worker_id of current lock holder
        "lock_granted_at": None,              # float | None — time.time() when lock was granted
        "clients":         {},                # dict[str, socket] — worker_id -> connected socket
        "state_lock":      threading.Lock(),  # guards lock_queue, lock_holder, clients
    }


# ---------------------------------------------------------------------------
# Task 2.19a — broadcast / unicast helpers
# Canonical snapshot pattern from Section 8.1 of the spec.
# RULE: never call send_json() while holding state_lock.
# ---------------------------------------------------------------------------

def broadcast(msg, state):
    """
    Send msg to every connected worker.

    Pattern:
      1. Acquire state_lock only long enough to copy the client dict.
      2. Release state_lock.
      3. Send to each socket outside the lock so slow/dead sockets
         cannot block the whole server.
    """
    # Step 1 — snapshot client list under the lock (fast, no I/O)
    with state["state_lock"]:
        recipients = list(state["clients"].items())  # [(worker_id, sock), ...]

    # Step 2 — send outside the lock (slow path, may block)
    for worker_id, sock in recipients:
        try:
            send_json(sock, msg)
        except OSError:
            # Socket already dead — handle_worker_disconnect will clean up
            # when its thread detects the error and exits.
            pass


def unicast(msg, worker_id, state):
    """
    Send msg to one specific worker.
    Same snapshot rule: snapshot the socket reference under the lock,
    then send outside it.
    """
    # Snapshot the target socket under the lock
    with state["state_lock"]:
        sock = state["clients"].get(worker_id)

    # Send outside the lock
    if sock is not None:
        try:
            send_json(sock, msg)
        except OSError:
            # Dead socket — thread will detect and clean up
            pass


# ---------------------------------------------------------------------------
# Task 2.18 — register_with_naming_server
# ---------------------------------------------------------------------------

def register_with_naming_server(ns_host, ns_port, my_ip, my_port):
    """
    Open a fresh TCP connection to the Naming Server and send a REGISTER
    request so workers can resolve the Lock Manager's address by name.

    Uses a fresh connection per Section 9 of the spec (open, transact, close).
    Raises RuntimeError if registration fails so start_lock_server can abort.
    """
    # Build the registration request — exact wire format from Section 9
    request = f"REGISTER {LOCK_SERVER_NAME} {my_ip} {my_port}\n"

    # Open a fresh TCP connection to the Naming Server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Connect to Naming Server
        sock.connect((ns_host, ns_port))

        # Send the REGISTER line
        sock.sendall(request.encode("utf-8"))

        # Read the response (OK or ERROR ...)
        response = sock.recv(1024).decode("utf-8").strip()

        # Log the outcome using Section 11 format
        print(f"[LM][--] REGISTER {LOCK_SERVER_NAME} -> {my_ip}:{my_port} — response: {response}")

        # Any response other than OK is a hard failure
        if response != "OK":
            raise RuntimeError(
                f"Naming Server rejected registration: {response}"
            )

    finally:
        # Always close the connection — do not reuse it
        sock.close()


# ---------------------------------------------------------------------------
# Task 2.19b — handle_hello
# ---------------------------------------------------------------------------

def handle_hello(msg, conn, state):
    """
    Process the initial hello message from a newly connected worker.

    Validation rules (per spec Section 16 / Task 2.19):
      - msg must contain a non-empty "worker_id" field
      - worker_id must not already be registered in state["clients"]

    On success:
      - Add worker_id -> conn to state["clients"]
      - Broadcast a queue_update so the new worker sees the current state
      - Return True

    On failure:
      - Send an error message to conn
      - Close conn
      - Return False
    """
    # Extract and validate worker_id
    worker_id = msg.get("worker_id", "").strip()

    if not worker_id:
        # Malformed hello — no worker_id
        error_msg = {
            "type":      "error",
            "message":   "hello message missing worker_id",
            "timestamp": state["clock"].tick(),
        }
        try:
            send_json(conn, error_msg)
        except OSError:
            pass
        conn.close()
        print(f"[LM][--] Rejected connection — missing worker_id")
        return False

    # Acquire state_lock to check and update clients atomically
    state["state_lock"].acquire()
    try:
        if worker_id in state["clients"]:
            # Duplicate ID — reject per CP-7
            state["state_lock"].release()

            error_msg = {
                "type":      "error",
                "message":   f"worker_id '{worker_id}' is already connected",
                "timestamp": state["clock"].tick(),
            }
            try:
                send_json(conn, error_msg)
            except OSError:
                pass
            conn.close()
            print(f"[LM][--] Rejected duplicate worker_id: {worker_id}")
            return False

        # Registration succeeds — store the connection
        state["clients"][worker_id] = conn

        # Build the initial queue_update to send back BEFORE releasing the lock
        # so that the snapshot is consistent.
        queue_snapshot = list(state["lock_queue"])
        holder_snapshot = state["lock_holder"]

    finally:
        # Release lock if it is still held (duplicate-ID path releases early)
        try:
            state["state_lock"].release()
        except RuntimeError:
            # Already released in the duplicate-ID branch
            pass

    # Build and broadcast queue_update outside the lock
    queue_update = build_queue_update_msg(
        state["clock"],
        holder_snapshot,
        queue_snapshot,
    )
    broadcast(queue_update, state)

    print(
        f"[LM][CLOCK={state['clock'].value()}] "
        f"Worker {worker_id} connected. "
        f"Total clients: {len(state['clients'])}"
    )
    return True


# ---------------------------------------------------------------------------
# Task 2.19c — handle_worker_disconnect
# ---------------------------------------------------------------------------

def handle_worker_disconnect(worker_id, state):
    """
    Called when a worker's socket closes unexpectedly (or after a clean quit).

    Actions (all under state_lock):
      1. Remove worker_id from state["clients"].
      2. Remove any queue entry for this worker.
      3. If this worker held the lock, release it and promote the next in queue.

    Broadcasts lock_released (if they held the lock) and queue_update
    OUTSIDE the lock to avoid deadlock.
    """
    # Flags set inside the lock, used outside to trigger broadcasts
    was_holder = False
    new_holder = None

    # Acquire state_lock for all mutations
    state["state_lock"].acquire()
    try:
        # Remove from client registry
        state["clients"].pop(worker_id, None)

        # Remove from lock queue
        state["lock_queue"] = [
            entry for entry in state["lock_queue"]
            if entry["worker_id"] != worker_id
        ]

        # Check if this worker held the lock
        if state["lock_holder"] == worker_id:
            was_holder = True

            if state["lock_queue"]:
                # Promote the next worker in line
                state["lock_holder"]     = state["lock_queue"][0]["worker_id"]
                state["lock_granted_at"] = time.time()
                new_holder               = state["lock_holder"]
            else:
                # Nobody is waiting — lock is now free
                state["lock_holder"]     = None
                state["lock_granted_at"] = None

        # Snapshot queue and holder for broadcast messages
        queue_snapshot  = list(state["lock_queue"])
        holder_snapshot = state["lock_holder"]

    finally:
        state["state_lock"].release()

    # --- Broadcasts outside the lock ---

    if was_holder:
        # Inform all workers that the previous holder's lock was released
        lock_released_msg = {
            "type":            "lock_released",
            "previous_holder": worker_id,
            "next_holder":     new_holder,
            "timestamp":       state["clock"].tick(),
        }
        broadcast(lock_released_msg, state)

        # Grant lock to the new holder (if any)
        if new_holder:
            lock_granted_msg = {
                "type":      "lock_granted",
                "worker_id": new_holder,
                "resource":  SHARED_RESOURCE_NAME,
                "timestamp": state["clock"].tick(),
            }
            unicast(lock_granted_msg, new_holder, state)
            print(
                f"[LM][CLOCK={state['clock'].value()}] "
                f"Lock transferred from {worker_id} (disconnect) to {new_holder}."
            )

    # Broadcast updated queue to all remaining workers
    queue_update = build_queue_update_msg(
        state["clock"],
        holder_snapshot,
        queue_snapshot,
    )
    broadcast(queue_update, state)

    print(
        f"[LM][CLOCK={state['clock'].value()}] "
        f"Worker {worker_id} disconnected."
    )


# ---------------------------------------------------------------------------
# Task 2.20a — process_request (stub promoted to full in Task 3.7,
# but the spec asks for a logging stub here; we implement it fully now
# since Members 2 & 3 are already done and merged).
# ---------------------------------------------------------------------------

def process_request(msg, state):
    """
    Handle a request_lock message from a worker.

    Steps:
      1. Update Lamport clock (receive rule).
      2. Add worker to queue.
      3. Sort queue by (timestamp, worker_id).
      4. If no current holder, grant lock to front of queue.
      5. Broadcast queue_update to all workers.
    """
    worker_id = msg.get("worker_id")
    timestamp = msg.get("timestamp", 0)

    # Note: clock.receive() is called in handle_worker immediately after
    # recv_json() per the Section 4 usage contract. Do NOT call it again here.

    # Variables set inside the lock, used outside for sends
    grant_to        = None
    queue_snapshot  = None
    holder_snapshot = None

    # Acquire state_lock for queue mutation
    state["state_lock"].acquire()
    try:
        # Ignore duplicate requests (worker already in queue or holds lock)
        already_in_queue = any(
            e["worker_id"] == worker_id for e in state["lock_queue"]
        )
        if already_in_queue or state["lock_holder"] == worker_id:
            print(
                f"[LM][CLOCK={state['clock'].value()}] "
                f"Ignoring duplicate request from {worker_id}."
            )
            return

        # Add request to queue
        state["lock_queue"].append({
            "worker_id": worker_id,
            "timestamp": timestamp,
        })

        # Sort queue: (timestamp, worker_id) ascending — Lamport fairness
        state["lock_queue"] = sort_queue(state["lock_queue"])

        # Grant lock immediately if nobody currently holds it
        if state["lock_holder"] is None:
            state["lock_holder"]     = state["lock_queue"][0]["worker_id"]
            state["lock_granted_at"] = time.time()
            grant_to                 = state["lock_holder"]

        # Snapshot state for broadcast messages
        queue_snapshot  = list(state["lock_queue"])
        holder_snapshot = state["lock_holder"]

    finally:
        state["state_lock"].release()

    # Log the current queue state
    queue_str = [(e["worker_id"], e["timestamp"]) for e in queue_snapshot]
    print(
        f"[LM][CLOCK={state['clock'].value()}] "
        f"request_lock from {worker_id} (ts={timestamp}). "
        f"Queue: {queue_str}"
    )

    # --- Sends outside the lock ---

    # Grant lock to the front of the queue if we just set a holder
    if grant_to:
        lock_granted_msg = {
            "type":      "lock_granted",
            "worker_id": grant_to,
            "resource":  SHARED_RESOURCE_NAME,
            "timestamp": state["clock"].tick(),
        }
        unicast(lock_granted_msg, grant_to, state)
        print(
            f"[LM][CLOCK={state['clock'].value()}] "
            f"Granted lock to {grant_to}."
        )

    # Broadcast queue state to all workers
    queue_update = build_queue_update_msg(
        state["clock"],
        holder_snapshot,
        queue_snapshot,
    )
    broadcast(queue_update, state)


# ---------------------------------------------------------------------------
# Task 2.20b — process_release (stub; full logic per spec)
# ---------------------------------------------------------------------------

def process_release(msg, state):
    """
    Handle a release_lock message from a worker.

    Steps:
      1. Validate the worker actually holds the lock.
      2. Remove them from the queue.
      3. Promote the next worker in line (if any).
      4. Broadcast lock_released and queue_update.
    """
    worker_id = msg.get("worker_id")
    timestamp = msg.get("timestamp", 0)

    # Note: clock.receive() is called in handle_worker immediately after
    # recv_json() per the Section 4 usage contract. Do NOT call it again here.

    # Variables set inside the lock
    previous_holder = None
    next_holder     = None
    queue_snapshot  = None
    holder_snapshot = None

    state["state_lock"].acquire()
    try:
        # Validate: only the actual holder can release
        if state["lock_holder"] != worker_id:
            state["state_lock"].release()

            error_msg = {
                "type":      "error",
                "message":   f"You do not hold the lock (holder is {state['lock_holder']}).",
                "timestamp": state["clock"].tick(),
            }
            unicast(error_msg, worker_id, state)
            print(
                f"[LM][CLOCK={state['clock'].value()}] "
                f"Spurious release from {worker_id} — ignored."
            )
            return

        # Record the outgoing holder before clearing
        previous_holder = worker_id

        # Remove the holder's entry from the queue
        state["lock_queue"] = [
            e for e in state["lock_queue"]
            if e["worker_id"] != worker_id
        ]

        # Promote next in line (if any)
        if state["lock_queue"]:
            state["lock_holder"]     = state["lock_queue"][0]["worker_id"]
            state["lock_granted_at"] = time.time()
            next_holder              = state["lock_holder"]
        else:
            state["lock_holder"]     = None
            state["lock_granted_at"] = None

        # Snapshot for broadcast messages
        queue_snapshot  = list(state["lock_queue"])
        holder_snapshot = state["lock_holder"]

    finally:
        try:
            state["state_lock"].release()
        except RuntimeError:
            pass  # Already released in the validation branch

    print(
        f"[LM][CLOCK={state['clock'].value()}] "
        f"{previous_holder} released lock. Next holder: {next_holder}."
    )

    # --- Sends outside the lock ---

    # Broadcast lock_released to all workers
    lock_released_msg = {
        "type":            "lock_released",
        "previous_holder": previous_holder,
        "next_holder":     next_holder,
        "timestamp":       state["clock"].tick(),
    }
    broadcast(lock_released_msg, state)

    # Grant lock to next holder (unicast)
    if next_holder:
        lock_granted_msg = {
            "type":      "lock_granted",
            "worker_id": next_holder,
            "resource":  SHARED_RESOURCE_NAME,
            "timestamp": state["clock"].tick(),
        }
        unicast(lock_granted_msg, next_holder, state)
        print(
            f"[LM][CLOCK={state['clock'].value()}] "
            f"Granted lock to {next_holder}."
        )

    # Broadcast updated queue to all workers
    queue_update = build_queue_update_msg(
        state["clock"],
        holder_snapshot,
        queue_snapshot,
    )
    broadcast(queue_update, state)


# ---------------------------------------------------------------------------
# Task 2.20c — handle_worker (per-connection thread)
# ---------------------------------------------------------------------------

def handle_worker(conn, addr, state):
    """
    Runs in a dedicated daemon thread for each connected worker.

    Protocol:
      - First message MUST be type "hello". Calls handle_hello.
        If handle_hello returns False, the connection was rejected — exit.
      - Subsequent messages: dispatch to process_request or process_release.
      - Unknown types: send an error response, continue loop.
      - On ConnectionError or OSError: call handle_worker_disconnect and exit.
    """
    worker_id = None  # resolved after hello

    try:
        # --- Step 1: receive and validate the hello message ---
        first_msg = recv_json(conn)

        # Update clock for received message (hello has no timestamp by design)
        # Per spec: do not call clock.receive() for messages without a timestamp.

        if first_msg.get("type") != "hello":
            error_msg = {
                "type":      "error",
                "message":   "First message must be type 'hello'.",
                "timestamp": state["clock"].tick(),
            }
            try:
                send_json(conn, error_msg)
            except OSError:
                pass
            conn.close()
            print(f"[LM][--] Connection from {addr} rejected — first message was not hello.")
            return

        # handle_hello registers the worker or closes conn and returns False
        if not handle_hello(first_msg, conn, state):
            return

        # Worker is now registered — extract their ID for cleanup on exit
        worker_id = first_msg.get("worker_id", "").strip()

        print(
            f"[LM][CLOCK={state['clock'].value()}] "
            f"[{worker_id}] Ready."
        )

        # --- Step 2: main message loop ---
        while True:
            msg = recv_json(conn)

            msg_type = msg.get("type", "")

            # Update Lamport clock on every message that carries a timestamp
            if "timestamp" in msg:
                state["clock"].receive(msg["timestamp"])

            if msg_type == "request_lock":
                process_request(msg, state)

            elif msg_type == "release_lock":
                process_release(msg, state)

            else:
                # Unknown message type — log and send error, do not crash
                print(
                    f"[LM][CLOCK={state['clock'].value()}] "
                    f"Unknown message type '{msg_type}' from {worker_id}."
                )
                error_msg = {
                    "type":      "error",
                    "message":   f"Unknown message type: '{msg_type}'",
                    "timestamp": state["clock"].tick(),
                }
                unicast(error_msg, worker_id, state)

    except ConnectionError as exc:
        # Clean disconnect or broken pipe
        print(
            f"[LM][--] Worker {worker_id or addr} disconnected: {exc}"
        )

    except OSError as exc:
        # Socket-level error
        print(
            f"[LM][--] Socket error for {worker_id or addr}: {exc}"
        )

    finally:
        # Always clean up on exit — releases lock if held, removes from queue
        if worker_id:
            handle_worker_disconnect(worker_id, state)
        else:
            conn.close()


# ---------------------------------------------------------------------------
# Task 2.20d — accept_loop
# ---------------------------------------------------------------------------

def accept_loop(server_sock, state):
    """
    Main accept loop. Runs in the main thread (or its own thread if needed).
    For each incoming connection, spawns a daemon thread running handle_worker.
    """
    while True:
        try:
            conn, addr = server_sock.accept()
            print(f"[LM][--] New connection from {addr}")

            # One daemon thread per worker — if main thread exits, these die too
            t = threading.Thread(
                target=handle_worker,
                args=(conn, addr, state),
                daemon=True,
            )
            t.start()

        except OSError:
            # Server socket closed (e.g., KeyboardInterrupt path)
            break


# ---------------------------------------------------------------------------
# Task 2.21 — start_lock_server and argparse entry point
# ---------------------------------------------------------------------------

def start_lock_server(port, ns_host, ns_port):
    """
    Full startup sequence for the Lock Manager:

      1. Detect local IP via get_local_ip().
      2. Register with the Naming Server.
      3. Initialize shared state.
      4. Bind TCP server socket.
      5. Start watchdog daemon thread (checks lock timeout every second).
      6. Print ready line.
      7. Enter accept_loop.
    """
    # Step 1 — detect our LAN IP for registration
    my_ip = get_local_ip()

    # Step 2 — register with Naming Server so workers can find us
    try:
        register_with_naming_server(ns_host, ns_port, my_ip, port)
    except Exception as exc:
        print(f"[LM][ERROR] Could not register with Naming Server: {exc}")
        sys.exit(1)

    # Step 3 — initialize shared state
    clock = LamportClock()
    state = _make_state(clock)

    # Step 4 — bind TCP server socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind(("", port))
        server_sock.listen(MAX_CONNECTIONS)
    except OSError as exc:
        print(f"[LM][ERROR] Could not bind to port {port}: {exc}")
        sys.exit(1)

    # Step 5 — watchdog daemon thread
    # Calls check_lock_timeout every second; auto-releases stale locks.
    def _watchdog():
        while True:
            check_lock_timeout(state, broadcast)
            time.sleep(1)

    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
    watchdog_thread.start()

    # Step 6 — ready line (Section 20 startup contract)
    ready_ts = clock.tick()
    print(f"[LM][CLOCK={ready_ts}] Lock Server ready on port {port}")

    # Step 7 — accept connections until interrupted
    try:
        accept_loop(server_sock, state)
    except KeyboardInterrupt:
        print("[LM][--] Shutting down.")
    finally:
        server_sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lock Manager — Distributed Cloud Resource Lock Manager"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=LOCK_SERVER_DEFAULT_PORT,
        help="Port for the Lock Manager to listen on (default: 9000)",
    )

    parser.add_argument(
        "--ns-host",
        default=NAMING_SERVER_HOST,
        help=f"Naming Server host (default: {NAMING_SERVER_HOST})",
    )

    parser.add_argument(
        "--ns-port",
        type=int,
        default=NAMING_SERVER_PORT,
        help=f"Naming Server port (default: {NAMING_SERVER_PORT})",
    )

    args = parser.parse_args()
    start_lock_server(args.port, args.ns_host, args.ns_port)

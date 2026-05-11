#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Member 2 — send_json, recv_json, get_local_ip
# Member 3 — LamportClock, sort_queue, build_queue_update_msg,
# simulate_resource_use, check_lock_timeout

import socket
import threading
import json
import struct
import time
from datetime import datetime
from config import *


# Member 2 — Networking Functions
def send_json(sock, msg):
    """
    Send JSON using length-prefixed framing.

    Format:
    [4-byte big-endian length][JSON payload]
    """

    try:
        payload = json.dumps(msg).encode("utf-8")
        header = struct.pack(">I", len(payload))

        sock.sendall(header)
        sock.sendall(payload)

    except OSError as e:
        raise ConnectionError(f"send_json failed: {e}")


def recv_json(sock):
    """
    Receive JSON using length-prefixed framing.
    Handles TCP fragmentation correctly.
    """

    # Read header (4 bytes)
    header = b""
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if chunk == b"":
            raise ConnectionError("Socket closed")
        header += chunk

    msg_length = struct.unpack(">I", header)[0]

    # Read payload
    data = b""
    while len(data) < msg_length:
        chunk = sock.recv(msg_length - len(data))
        if chunk == b"":
            raise ConnectionError("Socket closed")
        data += chunk

    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON received")


def get_local_ip():
    """
    Get local IP without sending real traffic.
    """

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("8.8.8.8", 80))  # no traffic actually sent
        ip = s.getsockname()[0]
    finally:
        s.close()

    return ip

#member 3
class LamportClock:
    """
    Thread-safe Lamport logical clock.
    """

    def __init__(self):
        """
        Initialize the clock value and thread lock.
        """

        # Starting logical clock value
        self._clock = INITIAL_CLOCK_VALUE

        # Lock used to protect shared clock access
        self._lock = threading.Lock()

    def value(self):
        """
        Safely return the current clock value.
        """

        # Acquire lock before reading shared data
        self._lock.acquire()

        try:
            # Read current clock value
            current_value = self._clock

        finally:
            # Always release the lock
            self._lock.release()

        return current_value

    def tick(self):
        """
        Increment clock for an internal event.
        """

        # Acquire lock before modifying clock
        self._lock.acquire()

        try:
            # Increase logical clock
            self._clock += 1

            # Store updated value
            new_value = self._clock

        finally:
            # Release lock after update
            self._lock.release()

        return new_value

    def send(self):
        """
        Increment clock before sending a message.
        """

        # Acquire lock before modifying clock
        self._lock.acquire()

        try:
            # Sending a message is a logical event
            self._clock += 1

            # Save updated value
            new_value = self._clock

        finally:
            # Release lock
            self._lock.release()

        return new_value

    def receive(self, received_timestamp):
        """
        Update clock after receiving a message.
        """

        # Acquire lock before modifying clock
        self._lock.acquire()

        try:
            # Lamport receive rule:
            # max(local_clock, received_clock) + 1
            self._clock = max(
                self._clock,
                received_timestamp
            ) + 1

            # Store updated value
            new_value = self._clock

        finally:
            # Release lock
            self._lock.release()

        return new_value


def sort_queue(queue):
    """
    Return a NEW queue sorted by:
    1. Lowest timestamp first
    2. Alphabetical worker_id if timestamps are equal
    """

    # Use sorted() to avoid mutating the original queue
    sorted_queue = sorted(
        queue,
        key=lambda item: (
            item["timestamp"],
            item["worker_id"]
        )
    )

    return sorted_queue


def build_queue_update_msg(clock, lock_holder, queue):
    """
    Build a queue_update message dictionary.
    """

    # Increment Lamport clock for this outgoing message
    timestamp = clock.tick()

    # Create message dictionary
    msg = {
        "type": "queue_update",
        "timestamp": timestamp,
        "lock_holder": lock_holder,
        "queue": queue
    }

    return msg


def simulate_resource_use(worker_id, resource, duration_sec):
    """
    Simulate resource usage by writing to the log file
    once per second.
    """

    # Open resource log file in append mode
    with open(
        RESOURCE_LOG_FILE,
        "a",
        encoding="utf-8"
    ) as log_file:

        # Loop once per second
        for tick in range(1, duration_sec + 1):

            # Current human-readable timestamp
            current_time = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            # Build log line
            log_line = (
                f"[{current_time}] "
                f"[{worker_id}] USING {resource} "
                f"tick={tick}\n"
            )

            # Write line to file
            log_file.write(log_line)

            # Force immediate write to disk
            log_file.flush()

            # Wait 1 second before next log entry
            time.sleep(1)


def check_lock_timeout(state, broadcast_fn):
    """
    Watchdog function that checks whether the current
    lock holder exceeded the maximum allowed hold time.
    """

    # Get current wall-clock time
    current_time = time.time()

    # Acquire shared state lock
    state["state_lock"].acquire()

    try:
        # Read current lock state
        lock_holder = state["lock_holder"]
        granted_at = state["lock_granted_at"]

        # If no active lock, nothing to check
        if lock_holder is None or granted_at is None:
            return

        # Calculate how long the lock has been held
        elapsed = current_time - granted_at

        # If timeout not exceeded, do nothing
        if elapsed < LOCK_MAX_HOLD_SEC:
            return

        # Log warning
        print(
            f"[LM][WARN] Worker "
            f"{lock_holder} exceeded lock timeout."
        )

        # Save old holder before clearing
        previous_holder = lock_holder

        # Remove timed-out worker from queue
        state["lock_queue"] = [
            item
            for item in state["lock_queue"]
            if item["worker_id"] != previous_holder
        ]

        # If queue still has workers
        if state["lock_queue"]:

            # Assign lock to next worker
            state["lock_holder"] = (
                state["lock_queue"][0]["worker_id"]
            )

            # Record new grant time
            state["lock_granted_at"] = time.time()

        else:
            # No waiting workers
            state["lock_holder"] = None
            state["lock_granted_at"] = None

        # Store updated holder
        new_holder = state["lock_holder"]

        # Build lock released message
        lock_released_msg = {
            "type": "lock_released",
            "worker_id": previous_holder,
            "timestamp": state["clock"].tick()
        }

        # Build updated queue message
        queue_update_msg = build_queue_update_msg(
            state["clock"],
            new_holder,
            state["lock_queue"]
        )

    finally:
        # Always release shared state lock
        state["state_lock"].release()

    # Broadcast messages OUTSIDE the lock
    # to avoid deadlocks

    # Notify all workers that lock was released
    broadcast_fn(lock_released_msg, state)

    # Notify all workers about updated queue state
    broadcast_fn(queue_update_msg, state)


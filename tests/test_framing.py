#!/usr/bin/env python3
# Placeholder tests for framing (send_json/recv_json)
# -*- coding: utf-8 -*-

import socket
import threading

from utils import send_json, recv_json


def print_result(test_name, passed):

    if passed:
        print(f"[PASS] {test_name}")

    else:
        print(f"[FAIL] {test_name}")


# ---------------------------------------------------
# Test 1 — Simple roundtrip
# ---------------------------------------------------

def test_roundtrip_simple():

    s1, s2 = socket.socketpair()

    try:
        original = {
            "type": "hello",
            "worker_id": "WA"
        }

        send_json(s1, original)

        received = recv_json(s2)

        print_result(
            "test_roundtrip_simple",
            received == original
        )

    finally:
        s1.close()
        s2.close()


# ---------------------------------------------------
# Test 2 — Unicode support
# ---------------------------------------------------

def test_roundtrip_unicode():

    s1, s2 = socket.socketpair()

    try:
        original = {
            "message": "こんにちは世界"
        }

        send_json(s1, original)

        received = recv_json(s2)

        print_result(
            "test_roundtrip_unicode",
            received == original
        )

    finally:
        s1.close()
        s2.close()


# ---------------------------------------------------
# Test 3 — Large payload
# ---------------------------------------------------

def test_roundtrip_large():

    s1, s2 = socket.socketpair()

    try:
        large_text = "A" * 100000

        original = {
            "data": large_text
        }

        send_json(s1, original)

        received = recv_json(s2)

        print_result(
            "test_roundtrip_large",
            received == original
        )

    finally:
        s1.close()
        s2.close()


# ---------------------------------------------------
# Test 4 — Partial recv simulation
# ---------------------------------------------------

class SlowSocket:
    """
    Wrapper that forces recv() to return 1 byte at a time.
    """

    def __init__(self, real_socket):
        self.real_socket = real_socket

    def recv(self, n):
        return self.real_socket.recv(1)

    def close(self):
        self.real_socket.close()


def test_partial_recv():

    s1, s2 = socket.socketpair()

    try:
        original = {
            "type": "queue_update",
            "queue": ["WA", "WB", "WC"]
        }

        send_json(s1, original)

        slow_socket = SlowSocket(s2)

        received = recv_json(slow_socket)

        print_result(
            "test_partial_recv",
            received == original
        )

    finally:
        s1.close()
        s2.close()


# ---------------------------------------------------
# Run all tests
# ---------------------------------------------------

if __name__ == "__main__":

    print("\nRunning framing tests...\n")

    test_roundtrip_simple()
    test_roundtrip_unicode()
    test_roundtrip_large()
    test_partial_recv()
    print("\nAll framing tests complete.\n")

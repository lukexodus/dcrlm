#!/usr/bin/env python3
# Naming server tests

import os
import socket
import sys
import threading
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
	sys.path.insert(0, ROOT_DIR)

from naming_server import start_naming_server


HOST = "127.0.0.1"
_SERVER_LOCK = threading.Lock()
_SERVER_STARTED = False
_SERVER_PORT = None


def _get_free_port():
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.bind((HOST, 0))
		return sock.getsockname()[1]


def _ensure_server():
	global _SERVER_STARTED, _SERVER_PORT
	with _SERVER_LOCK:
		if _SERVER_STARTED:
			return _SERVER_PORT
		port = _get_free_port()
		thread = threading.Thread(
			target=start_naming_server,
			args=(HOST, port),
			daemon=True,
		)
		thread.start()
		time.sleep(0.1)
		_SERVER_STARTED = True
		_SERVER_PORT = port
		return port


def _send_line(line):
	port = _ensure_server()
	with socket.create_connection((HOST, port), timeout=2) as sock:
		sock.sendall((line + "\n").encode())
		return sock.recv(1024).decode().strip()


def _unique_name(prefix):
	return f"{prefix}_{time.time_ns()}"


def test_register_and_lookup():
	name = _unique_name("svc")
	resp = _send_line(f"REGISTER {name} 127.0.0.1 9000")
	assert resp == "OK"
	resp = _send_line(f"LOOKUP {name}")
	assert resp == "FOUND 127.0.0.1 9000"


def test_lookup_missing():
	name = _unique_name("missing")
	resp = _send_line(f"LOOKUP {name}")
	assert resp == "NOT_FOUND"


def test_re_register():
	name = _unique_name("svc")
	resp = _send_line(f"REGISTER {name} 127.0.0.1 9000")
	assert resp == "OK"
	resp = _send_line(f"REGISTER {name} 127.0.0.1 9001")
	assert resp == "OK"
	resp = _send_line(f"LOOKUP {name}")
	assert resp == "FOUND 127.0.0.1 9001"


def test_concurrent_requests():
	names = [_unique_name(f"svc{i}") for i in range(10)]

	def _register(name):
		resp = _send_line(f"REGISTER {name} 127.0.0.1 9000")
		assert resp == "OK"

	threads = [threading.Thread(target=_register, args=(name,)) for name in names]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()

	for name in names:
		resp = _send_line(f"LOOKUP {name}")
		assert resp == "FOUND 127.0.0.1 9000"


def _run_test(fn):
	try:
		fn()
		print(f"PASS: {fn.__name__}")
	except Exception as exc:
		print(f"FAIL: {fn.__name__} -> {exc}")


if __name__ == "__main__":
	for test in [
		test_register_and_lookup,
		test_lookup_missing,
		test_re_register,
		test_concurrent_requests,
	]:
		_run_test(test)

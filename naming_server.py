#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Member 1 — Registry Architect
# Naming Server: handles REGISTER and LOOKUP requests.

import socket
import threading
import sys
import argparse
from config import NAMING_SERVER_HOST, NAMING_SERVER_PORT, MAX_CONNECTIONS


def handle_register(tokens, registry, registry_lock):
	"""Handle a REGISTER request and update the registry."""
	# Validate the basic request shape before touching shared state.
	if len(tokens) < 4:
		return "ERROR malformed REGISTER request"

	# Extract the fields in the wire format order.
	_, name, ip, port_text = tokens[:4]

	# Convert the port to an integer before acquiring the lock.
	try:
		port = int(port_text)
	except ValueError:
		return "ERROR invalid port"

	# Update the shared registry atomically.
	with registry_lock:
		registry[name] = (ip, port)

	# Registration always succeeds, including re-registration.
	return "OK"


def handle_lookup(tokens, registry, registry_lock):
	"""Handle a LOOKUP request and return the registered address."""
	# Validate that the request includes the logical name.
	if len(tokens) < 2:
		return "ERROR malformed LOOKUP request"

	# Extract the logical service name from the request tokens.
	_, name = tokens[:2]

	# Read the shared registry atomically.
	with registry_lock:
		entry = registry.get(name)

	# Format the response based on whether the name was found.
	if entry is None:
		return "NOT_FOUND"

	ip, port = entry
	return f"FOUND {ip} {port}"


def handle_client(conn, addr, registry, registry_lock):
	"""Handle one TCP client connection for the naming server."""
	try:
		# Read a single newline-terminated request line from the client.
		data = b""
		while not data.endswith(b"\n"):
			chunk = conn.recv(1024)
			if not chunk:
				break
			data += chunk

		# Decode and split the request into tokens.
		line = data.decode().strip()
		tokens = line.split() if line else []

		# Log every request using the shared format.
		print(f"[NS][--] {line if line else 'EMPTY REQUEST'}")

		# Dispatch based on the first token, or return an error for unknown input.
		if not tokens:
			response = "ERROR empty request"
		elif tokens[0] == "REGISTER":
			response = handle_register(tokens, registry, registry_lock)
		elif tokens[0] == "LOOKUP":
			response = handle_lookup(tokens, registry, registry_lock)
		else:
			response = "ERROR unknown command"

		# Send the response back to the client as a newline-terminated line.
		conn.sendall((response + "\n").encode())
	except OSError as exc:
		print(f"[NS][--] Socket error: {exc}")
	finally:
		# Always close the client socket when the request is complete.
		conn.close()


def start_naming_server(host, port):
	"""Main entry point. Binds socket, accepts connections in a loop."""
	registry = {}
	registry_lock = threading.Lock()

	server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	try:
		server_sock.bind((host, port))
		server_sock.listen(MAX_CONNECTIONS)
		print(f"[NS][--] Naming Server ready on port {port}")

		while True:
			conn, addr = server_sock.accept()
			thread = threading.Thread(
				target=handle_client,
				args=(conn, addr, registry, registry_lock),
				daemon=True,
			)
			thread.start()
	except KeyboardInterrupt:
		print("[NS][--] Shutting down.")
	finally:
		server_sock.close()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Naming Server")
	parser.add_argument("--host", default=NAMING_SERVER_HOST)
	parser.add_argument("--port", type=int, default=NAMING_SERVER_PORT)
	args = parser.parse_args()
	start_naming_server(args.host, args.port)
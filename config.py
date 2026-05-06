#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Shared configuration. Do not modify without team agreement.

# Naming Server — the ONE hardcoded address in the entire system
NAMING_SERVER_HOST = "127.0.0.1"   # change to LAN IP during multi-machine testing
NAMING_SERVER_PORT = 5000

# Logical service names (keys in the naming registry)
LOCK_SERVER_NAME = "lock.server.main"

# Lock Server default port (used only for initial registration)
LOCK_SERVER_DEFAULT_PORT = 9000

# Networking
SOCKET_TIMEOUT_SEC    = 5.0    # how long to wait on a blocking recv before giving up
MAX_CONNECTIONS       = 10     # backlog for socket.listen()
MESSAGE_HEADER_BYTES  = 4      # length prefix size (big-endian unsigned int)
RECV_BUFFER_SIZE      = 4096   # bytes per recv() call

# Lamport Clock
INITIAL_CLOCK_VALUE   = 0

# Resource being protected
SHARED_RESOURCE_NAME  = "gpu_0"

# Worker ID tie-breaking (lower = higher priority at same timestamp)
# Workers are identified by string; Python string comparison handles tie-breaking
# e.g. "WA" < "WB" < "WC"

# Lock timeout
LOCK_MAX_HOLD_SEC = 30        # worker auto-released after this many seconds

# Shared resource log file
RESOURCE_LOG_FILE = "resource_access.log"

# Multi-machine backup (comment out the above and uncomment these)
# NAMING_SERVER_HOST = "192.168.1.XX"   # replace XX with Naming Server machine's LAN IP
# NAMING_SERVER_PORT = 5000


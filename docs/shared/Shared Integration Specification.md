# DCRLM — Shared Integration Specification

_This document is the single source of truth. All five members read this before writing a single line of code._

---

## 1. Project File Structure

Every member works within this layout. No deviations.

```
dcrlm/
├── naming_server.py      Member 1
├── lock_server.py        Member 5
├── worker_client.py      Member 4
├── utils.py              Members 2 & 3  ← shared library, everyone imports this
├── config.py             Everyone reads this, nobody modifies without team agreement
├── requirements.txt      One line: (none, stdlib only)
└── tests/
    ├── test_clock.py     Member 3 writes, everyone runs
    ├── test_framing.py   Member 2 writes, everyone runs
    └── test_naming.py    Member 1 writes, everyone runs
```

---

## 2. `config.py` — Global Constants

This is the only file where numbers and strings are defined. Everyone imports from here. Nobody hardcodes anything anywhere else.

```python
# config.py
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
```

---

## 3. Message Schema — Complete Specification

Every message in the system is a JSON object sent over TCP with a 4-byte length prefix (see Section 5). Every message has a `type` field. All other fields depend on `type`.

### 3.1 Worker → Lock Manager

```json
{
    "type": "hello",
    "worker_id": "WA"
}
```

_Sent immediately after TCP connection is established. Registers the worker with the server._

---

```json
{
    "type": "request_lock",
    "worker_id": "WA",
    "timestamp": 7,
    "resource": "gpu_0"
}
```

_Worker wants the lock. `timestamp` is the worker's Lamport clock value at send time (after applying Rule 2)._

---

```json
{
    "type": "release_lock",
    "worker_id": "WA",
    "timestamp": 12
}
```

_Worker is done with the resource. `timestamp` is the Lamport clock value at send time._

### 3.2 Lock Manager → Worker (Unicast — one worker only)

```json
{
    "type": "lock_granted",
    "worker_id": "WA",
    "resource": "gpu_0",
    "timestamp": 9
}
```

_Sent only to the worker at the front of the queue. `timestamp` is the Lock Manager's Lamport clock at send time._

---

```json
{
    "type": "error",
    "message": "You already hold the lock.",
    "timestamp": 10
}
```

_Sent when a worker does something invalid (requests a lock it already holds, releases a lock it does not hold)._

### 3.3 Lock Manager → All Workers (Broadcast)

```json
{
    "type": "queue_update",
    "timestamp": 11,
    "lock_holder": "WA",
    "queue": [
        {"worker_id": "WA", "timestamp": 3},
        {"worker_id": "WB", "timestamp": 3},
        {"worker_id": "WC", "timestamp": 5}
    ]
}
```

_Sent to ALL connected workers whenever the queue changes (on request, on grant, on release). `queue` is always sorted by `(timestamp, worker_id)` ascending. `lock_holder` is `null` if no one holds the lock._

---

```json
{
    "type": "lock_released",
    "previous_holder": "WA",
    "next_holder": "WB",
    "timestamp": 14
}
```

_Sent to ALL workers when a lock is released. `next_holder` is `null` if the queue is now empty._

### 3.4 Lock Manager ↔ Naming Server

These are sent as raw newline-terminated strings (not JSON, not length-prefixed) because the Naming Server is simpler and purpose-built.

```
REGISTER lock.server.main 192.168.1.10 9000\n
```

_Lock Manager sends this on startup and on restart._

```
OK\n
```

_Naming Server confirms registration._

```
LOOKUP lock.server.main\n
```

_Worker or Lock Manager sends this to resolve a name._

```
FOUND 192.168.1.10 9000\n
```

_Naming Server responds with IP and port._

```
NOT_FOUND\n
```

_Naming Server responds if the name is not registered._

---

## 4. `LamportClock` Interface

Member 3 writes this class in `utils.py`. Everyone else instantiates and calls it. The interface is fixed — Members 4 and 5 depend on it.

```python
class LamportClock:
    """
    Thread-safe Lamport Logical Clock.
    All methods acquire an internal lock before modifying state.
    """

    def __init__(self):
        """Initialize clock to INITIAL_CLOCK_VALUE from config."""

    def tick(self) -> int:
        """
        Rule 1 — local event.
        Increment clock by 1. Return the new value.
        Call before any significant local event that is not a send or receive.
        """

    def send(self) -> int:
        """
        Rule 2 — sending a message.
        Increment clock by 1. Return the new value to attach to the outgoing message.
        Call immediately before send_json(). Use the returned value as 'timestamp'.
        """

    def receive(self, received_timestamp: int) -> int:
        """
        Rule 3 — receiving a message.
        Set clock = max(self.clock, received_timestamp) + 1.
        Return the new value.
        Call immediately after recv_json(), passing msg['timestamp'].
        """

    def value(self) -> int:
        """
        Return the current clock value without modifying it.
        Use for display and logging only.
        """
```

**Usage contract** — every member must follow this exactly:

```python
# SENDING a message:
ts = clock.send()
send_json(sock, {"type": "request_lock", "worker_id": wid, "timestamp": ts, "resource": SHARED_RESOURCE_NAME})

# RECEIVING a message:
msg = recv_json(sock)
clock.receive(msg["timestamp"])   # always call this on every received message that has a timestamp
# then handle msg["type"]
```

Messages from the Naming Server (raw strings) do not carry timestamps — do not call `clock.receive()` for those.

---

## 5. `send_json` / `recv_json` Interface

Member 2 writes these in `utils.py`. Everyone else calls them. The interface is fixed.

```python
def send_json(sock: socket.socket, msg: dict) -> None:
    """
    Serialize msg to JSON, prefix with a 4-byte big-endian length header,
    and send the entire payload over sock.

    Raises: ConnectionError if the socket is closed or broken.
    """

def recv_json(sock: socket.socket) -> dict:
    """
    Read a 4-byte big-endian length header from sock.
    Then read exactly that many bytes.
    Deserialize and return the dict.

    Raises: ConnectionError if the socket is closed or broken.
            ValueError if the payload is not valid JSON.
    """
```

**Wire format:**

```
[ 4 bytes: big-endian uint32 = N ][ N bytes: UTF-8 JSON string ]
```

Example — the message `{"type":"hello","worker_id":"WA"}` (32 bytes):

```
00 00 00 20 7b 22 74 79 70 65 22 3a 22 68 65 6c 6c 6f 22 ...
|--header-| |------------------JSON body------------------
```

**Everyone must use `send_json`/`recv_json` for all Lock Manager ↔ Worker communication.** Only the Naming Server uses raw strings (it predates the framing layer by design — simpler to test standalone).

**Broadcast Snapshot Pattern (Canonical Code)**

Replace the note in Section 5 with this. Member 5 copies this pattern exactly into `lock_server.py`. Member 3 reviews it.

```python
def broadcast(msg: dict, state: dict) -> None:
    """
    Sends msg to all connected workers.
    RULE: Never call send_json() while holding state_lock.
    Pattern: snapshot the client dict under the lock, then send outside it.
    """
    # Step 1 — snapshot under lock (fast, no I/O)
    with state["state_lock"]:
        recipients = list(state["clients"].items())  # [(worker_id, sock), ...]

    # Step 2 — send outside lock (slow, may block)
    for worker_id, sock in recipients:
        try:
            send_json(sock, msg)
        except OSError:
            # Socket already dead — do not crash, do not re-acquire lock here
            # handle_worker_disconnect will clean this up when its thread exits
            pass


def unicast(msg: dict, worker_id: str, state: dict) -> None:
    """
    Sends msg to one specific worker.
    Same snapshot rule applies — never hold state_lock while sending.
    """
    with state["state_lock"]:
        sock = state["clients"].get(worker_id)

    if sock is not None:
        try:
            send_json(sock, msg)
        except OSError:
            pass
```

---

## 6. Worker ID Convention

Worker IDs are strings chosen by the worker at launch (passed as a command-line argument). They must be:

- Unique across all connected workers in a session
- Non-empty strings
- No spaces (they appear in log lines)

Recommended format for demos: `"WA"`, `"WB"`, `"WC"` — but the system must not assume this format. Tie-breaking uses Python's default string comparison (`"WA" < "WB"` is `True`).

---

## 7. Queue Sorting Contract

Member 3 writes this logic. Member 5 calls it inside `lock_server.py`. The sort key is fixed and must not be changed unilaterally.

```python
# Inside lock_server.py — the queue is a list of dicts
queue.sort(key=lambda entry: (entry["timestamp"], entry["worker_id"]))
```

Queue entries are dicts with exactly two fields:

```python
{"worker_id": "WA", "timestamp": 3}
```

The front of the queue (`queue[0]`) is always the next candidate to receive the lock.

---

## 8. Server-Side State Schema

Member 5 owns this state inside `lock_server.py`. Members 3's clock logic and Member 2's socket utilities both operate on it. The field names and types are fixed so that Member 3 can write queue logic against them without needing to see Member 5's full file.

```python
# All mutable state in lock_server.py

clock           : LamportClock          # one instance, shared across all threads
lock_queue      : list[dict]            # [{"worker_id": str, "timestamp": int}, ...]
lock_holder     : str | None            # worker_id of current holder, or None
lock_granted_at : float | None          # time.time() value when lock was granted, or None
clients         : dict[str, socket]     # worker_id -> connected socket
state_lock      : threading.Lock()      # acquired before reading/writing any of the above
```

**The `state_lock` rule:** Any thread that reads or writes `lock_queue`, `lock_holder`, or `clients` must hold `state_lock`. The only exception is reading `clock.value()` for display purposes.

```python
# Correct pattern:
with state_lock:
    lock_queue.append({"worker_id": wid, "timestamp": ts})
    lock_queue.sort(key=lambda e: (e["timestamp"], e["worker_id"]))
    if lock_holder is None:
        lock_holder = lock_queue[0]["worker_id"]
        grant_to = lock_holder
# send grant outside the lock — never block inside state_lock
if grant_to:
    send_json(clients[grant_to], {"type": "lock_granted", ...})
```

## 8.1 — Broadcast and Unicast: Canonical Code Pattern

This is the authoritative implementation pattern for sending messages from the Lock Manager to workers. Member 5 copies this exactly. Member 3 reviews it before integration.

**The rule in one sentence:** Never call `send_json()` while holding `state_lock`.

The reason: `send_json()` writes to a socket, which can block if the receiving buffer is full or if the connection is slow. If the lock is held during that block, every other thread that needs `state_lock` — including threads receiving new messages from other workers — freezes. The entire server deadlocks.

The fix is a two-step snapshot pattern:

```python
def broadcast(msg: dict, state: dict) -> None:
    """
    Sends msg to all connected workers.
    RULE: Never call send_json() while holding state_lock.
    Pattern: snapshot the client dict under the lock, then send outside it.
    """
    # Step 1 — snapshot under lock (fast, no I/O)
    with state["state_lock"]:
        recipients = list(state["clients"].items())  # [(worker_id, sock), ...]

    # Step 2 — send outside lock (slow, may block)
    for worker_id, sock in recipients:
        try:
            send_json(sock, msg)
        except OSError:
            # Socket already dead — do not crash, do not re-acquire lock here.
            # handle_worker_disconnect will clean this up when its thread exits.
            pass


def unicast(msg: dict, worker_id: str, state: dict) -> None:
    """
    Sends msg to one specific worker.
    Same snapshot rule applies — never hold state_lock while sending.
    """
    with state["state_lock"]:
        sock = state["clients"].get(worker_id)

    if sock is not None:
        try:
            send_json(sock, msg)
        except OSError:
            pass
```

---

## 9. Naming Server Protocol — Exact Format

Member 1 implements this. Members 4 and 5 send these strings. The format is exact — trailing newline included, no extra whitespace.

```python
# Sending a REGISTER request (lock_server.py):
sock.sendall(f"REGISTER {LOCK_SERVER_NAME} {my_ip} {my_port}\n".encode())
response = sock.recv(1024).decode().strip()
# response == "OK"

# Sending a LOOKUP request (worker_client.py):
sock.sendall(f"LOOKUP {LOCK_SERVER_NAME}\n".encode())
response = sock.recv(1024).decode().strip()
# response == "FOUND 192.168.1.10 9000"
# or        == "NOT_FOUND"

# Parsing FOUND response:
_, ip, port_str = response.split()
port = int(port_str)
```

Each REGISTER and LOOKUP uses a **fresh TCP connection** to the Naming Server. Open, transact, close. Do not reuse the connection.

---

## 10. Error Handling Contracts

These behaviors must be consistent across all files.

|Situation|Required behavior|
|---|---|
|`recv_json` gets 0 bytes|Raise `ConnectionError("Socket closed")`|
|Worker disconnects while holding lock|Server releases the lock automatically, broadcasts `lock_released` with `next_holder`|
|Worker disconnects while in queue|Server removes them from queue, broadcasts `queue_update`|
|Worker sends unknown `type`|Server sends `error` message back, ignores the request, does not crash|
|Naming Server returns `NOT_FOUND`|Client prints error and exits with code 1|
|Any socket operation raises `OSError`|Catch, log, close that socket cleanly, continue serving other clients|

---

## 11. Logging Convention

Every process prints to stdout with a consistent format. No external logging library. Use `print()`.

```
[PROCESS_TAG][CLOCK=N] event description
```

Examples:

```
[NS]      [--] REGISTER lock.server.main -> 192.168.1.10:9000
[LM][CLOCK=4]  Received request_lock from WA (ts=3). Queue: [(3,WA),(3,WB)]
[LM][CLOCK=7]  Granted lock to WA.
[WA][CLOCK=8]  Lock granted. Accessing resource gpu_0.
[WA][CLOCK=12] Releasing lock.
[LM][CLOCK=13] WA released lock. Next holder: WB.
[WB][CLOCK=14] Lock granted. Accessing resource gpu_0.
```

The Naming Server uses `--` for clock since it has no Lamport clock. All others use their current clock value at the moment of the print.

---

## 12. Python Version & Dependencies

- **Python 3.10 or higher** — required for `str | None` type hints and `match` statements
- **Standard library only** — no pip installs
- Modules used: `socket`, `threading`, `json`, `struct`, `sys`, `argparse`, `time`

Every file begins with:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
```

---

## 13. Command-Line Interface Per Program

Every program accepts arguments via `argparse`. No interactive prompts for configuration.

```bash
# Naming Server
python naming_server.py --port 5000

# Lock Manager
python lock_server.py --port 9000 --ns-host 127.0.0.1 --ns-port 5000

# Worker Client
python worker_client.py --id WA --ns-host 127.0.0.1 --ns-port 5000
```

All arguments have defaults matching `config.py` so running with no arguments works on a single machine.

---

## 14. Integration Checkpoints

These are the agreed handoff tests. A member's work is not "done" until the relevant checkpoint passes. Member 5 runs all checkpoints during Phase 3.

| Checkpoint | What to run                                                                                   | Expected result                                                                           |
| ---------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| CP-1       | Start `naming_server.py`. Send `REGISTER` and `LOOKUP` manually via `netcat` or a test script | `OK` and `FOUND` responses                                                                |
| CP-2       | Run `tests/test_framing.py`                                                                   | `send_json` → `recv_json` round-trip returns identical dict                               |
| CP-3       | Run `tests/test_clock.py`                                                                     | All three Lamport rules produce correct values; thread-safety test passes                 |
| CP-4       | Start NS + LM. Connect one Worker. Send `hello`                                               | LM logs worker registered; Worker receives no error                                       |
| CP-5       | Start NS + LM. Connect three Workers. All request lock simultaneously                         | Lock granted to lowest `(ts, id)`; others receive `queue_update`; lock releases correctly |
| CP-6       | CP-5 with `time.sleep(2)` in one Worker's send path                                           | Same winner as without sleep — Lamport order holds                                        |
| CP-7       | Connect a Worker with an ID already in use                                                    | LM sends `error`, closes new connection, existing worker unaffected                       |
| CP-8       | Worker holds lock for longer than `LOCK_MAX_HOLD_SEC`                                         | LM watchdog releases lock, broadcasts `lock_released`, next worker granted                |
| CP-9       | Open `resource_access.log` after a 3-worker run                                               | No two worker IDs interleaved in the log                                                  |

---

## 15. What Each Member Must Never Do

These are cross-cutting rules, not suggestions.

| Member | Must never                                                                                       |
| ------ | ------------------------------------------------------------------------------------------------ |
| All    | Import anything not in the Python standard library                                               |
| All    | Hardcode any IP, port, or name outside `config.py`                                               |
| All    | Call `clock.receive()` on messages that have no `timestamp` field                                |
| All    | Modify `utils.py` without telling the whole team                                                 |
| All    | Push directly to `main` branch — use pull requests                                               |
| 4, 5   | Change the `LamportClock` interface — only Member 3 does that                                    |
| 4, 5   | Change `send_json`/`recv_json` — only Member 2 does that                                         |
| 1      | Use `send_json`/`recv_json` — Naming Server uses raw strings by design                           |
| 5      | Read or write `lock_queue`, `lock_holder`, or `clients` without holding `state_lock`             |
| 5      | Call `send_json()` or any blocking I/O while holding `state_lock`                                |
| 5      | Accept a second connection with an already-registered `worker_id` — reject and close immediately |
| 4      | Assume connection success — always handle the `error` message type on connect                    |
| All    | Hold `state_lock` for more than a snapshot read/write — no I/O, no sleeps inside the lock        |

---

## 16. Complete Function Signatures — All Files

Every member knows exactly what to call from every other member's code, even before the implementation exists. Stub these out on day one.

### `utils.py` — complete

```python
# Member 2 implements these
def send_json(sock: socket.socket, msg: dict) -> None: ...
def recv_json(sock: socket.socket) -> dict: ...

# Member 3 implements these
class LamportClock:
    def __init__(self) -> None: ...
    def tick(self) -> int: ...
    def send(self) -> int: ...
    def receive(self, received_timestamp: int) -> int: ...
    def value(self) -> int: ...

def sort_queue(queue: list[dict]) -> list[dict]:
    """
    Takes a list of {"worker_id": str, "timestamp": int} dicts.
    Returns a new list sorted by (timestamp, worker_id) ascending.
    Does not mutate the input list.
    Member 3 writes this. Member 5 calls it.
    """
    ...

def build_queue_update_msg(clock: LamportClock, lock_holder: str | None, queue: list[dict]) -> dict:
    """
    Constructs the standard queue_update broadcast message dict.
    Member 3 writes this. Member 5 calls it after every queue change.
    """
    ...
    
def simulate_resource_use(worker_id: str, resource: str, duration_sec: float) -> None:
    """
    Simulates a worker using the shared resource.
    Writes one entry to RESOURCE_LOG_FILE per second for duration_sec seconds.
    Each line proves exclusive access by including worker_id, resource, and a sequence number.

    Log line format (one per second):
        [TIMESTAMP] [worker_id] USING [resource] tick=N

    Example:
        [2024-01-01 12:00:01] [WA] USING gpu_0 tick=1
        [2024-01-01 12:00:02] [WA] USING gpu_0 tick=2

    Member 4 calls this from worker_client.py after receiving lock_granted.
    The file is opened in append mode. No file locking needed —
    mutual exclusion is guaranteed by the lock protocol itself.
    """
    ...

def check_lock_timeout(state: dict) -> None:
    """
    Watchdog function. Member 5 calls this in a dedicated daemon thread
    that runs an infinite loop with time.sleep(1).

    Logic:
        if lock_holder is not None
        and lock_granted_at is not None
        and (time.time() - lock_granted_at) >= LOCK_MAX_HOLD_SEC:
            treat as if that worker sent release_lock
            log a warning
            broadcast lock_released
            broadcast queue_update

    Acquires state_lock only for the snapshot check and state mutation.
    Calls broadcast() outside the lock.
    """
    ...
```

### `naming_server.py` — complete

```python
def start_naming_server(host: str, port: int) -> None:
    """Main entry point. Binds socket, accepts connections in a loop."""
    ...

def handle_client(conn: socket.socket, addr: tuple, registry: dict, registry_lock: threading.Lock) -> None:
    """
    Runs in its own thread per connection.
    Reads one line, dispatches to handle_register or handle_lookup, closes connection.
    """
    ...

def handle_register(tokens: list[str], registry: dict, registry_lock: threading.Lock) -> str:
    """
    tokens = ["REGISTER", "lock.server.main", "192.168.1.10", "9000"]
    Updates registry. Returns "OK" or "ERROR <reason>".
    """
    ...

def handle_lookup(tokens: list[str], registry: dict, registry_lock: threading.Lock) -> str:
    """
    tokens = ["LOOKUP", "lock.server.main"]
    Returns "FOUND 192.168.1.10 9000" or "NOT_FOUND".
    """
    ...


def handle_hello(msg: dict, conn: socket.socket, state: dict) -> bool:
    """
    Handles the initial hello message from a connecting worker.
    Returns True if registration succeeded, False if rejected.

    Rejection conditions:
        - msg has no "worker_id" field
        - worker_id is empty string
        - worker_id already exists in state["clients"]

    On rejection:
        send error message to conn
        close conn
        return False

    On success:
        add worker_id -> conn to state["clients"] under state_lock
        broadcast queue_update to all workers
        return True

    Called from handle_worker() before entering the main message loop.
    If this returns False, handle_worker() exits immediately.
    """
    ...
```

### `lock_server.py` — complete

```python
def start_lock_server(port: int, ns_host: str, ns_port: int) -> None:
    """Registers with NS, binds socket, starts accept loop."""
    ...

def register_with_naming_server(ns_host: str, ns_port: int, my_ip: str, my_port: int) -> None:
    """Sends REGISTER to NS. Raises ConnectionError if NS is unreachable."""
    ...

def accept_loop(server_sock: socket.socket, state: dict) -> None:
    """Accepts new connections. Spawns handle_worker thread for each."""
    ...

def handle_worker(conn: socket.socket, addr: tuple, state: dict) -> None:
    """
    Runs in its own thread per worker.
    Reads messages in a loop. Dispatches to process_request or process_release.
    On disconnect: calls handle_worker_disconnect.
    """
    ...

def process_request(msg: dict, state: dict) -> None:
    """
    Handles type == "request_lock".
    Acquires state_lock. Adds to queue. Sorts. Grants if no holder. Broadcasts queue_update.
    """
    ...

def process_release(msg: dict, state: dict) -> None:
    """
    Handles type == "release_lock".
    Acquires state_lock. Removes holder. Promotes next in queue. Broadcasts lock_released and queue_update.
    """
    ...

def handle_worker_disconnect(worker_id: str, state: dict) -> None:
    """
    Called when a worker's socket closes unexpectedly.
    Removes from clients and queue. If they held the lock, releases it.
    Broadcasts queue_update.
    """
    ...

def broadcast(msg: dict, state: dict) -> None:
    """
    Sends msg to all connected workers via send_json.
    Acquires state_lock only to get a snapshot of clients, then releases before sending.
    Never sends to a client whose socket has closed — catches and logs silently.
    """
    ...

def unicast(msg: dict, worker_id: str, state: dict) -> None:
    """Sends msg to one specific worker. Catches socket errors silently."""
    ...
```

### `worker_client.py` — complete

```python
def start_worker(worker_id: str, ns_host: str, ns_port: int) -> None:
    """Resolves LM address, connects, sends hello, starts listener thread, starts input loop."""
    ...

def resolve_lock_server(ns_host: str, ns_port: int) -> tuple[str, int]:
    """
    Sends LOOKUP to NS. Returns (ip, port).
    Exits with code 1 if NOT_FOUND.
    """
    ...

def listener_thread(sock: socket.socket, clock: LamportClock, state: dict) -> None:
    """
    Runs in background thread.
    Reads broadcast messages from LM in a loop.
    Calls clock.receive() on every message.
    Updates shared state dict and prints to terminal.
    """
    ...

def input_loop(sock: socket.socket, clock: LamportClock, worker_id: str, state: dict) -> None:
    """
    Main thread. Accepts keyboard input.
    Commands: 'request', 'release', 'status', 'quit'.
    """
    ...

def send_request(sock: socket.socket, clock: LamportClock, worker_id: str) -> None:
    """Calls clock.send(), sends request_lock message."""
    ...

def send_release(sock: socket.socket, clock: LamportClock, worker_id: str) -> None:
    """Calls clock.send(), sends release_lock message."""
    ...
    
def handle_connect_response(sock: socket.socket) -> bool:
    """
    Called immediately after sending hello.
    Waits briefly for either a queue_update (success) or error (rejection).

    On error message received:
        print the error message to terminal
        close socket
        return False

    On queue_update received:
        print connected successfully
        return True

    On timeout (SOCKET_TIMEOUT_SEC exceeded):
        print connection timed out
        close socket
        return False

    If this returns False, start_worker() exits with code 1.
    """
    ...
```

---

## 17. Shared `state` Dict — Worker Side

The `listener_thread` and `input_loop` in `worker_client.py` share a small state dict so the UI can display current status without race conditions on individual variables.

```python
# Initialized in start_worker(), passed to both threads
state = {
    "holds_lock":    False,          # bool — does this worker currently hold the lock?
    "queue_position": None,          # int or None — this worker's position in the queue
    "lock_holder":   None,           # str or None — who currently holds the lock
    "queue":         [],             # list of {"worker_id", "timestamp"} — full queue snapshot
    "state_lock":    threading.Lock()
}
```

`listener_thread` writes to this under `state["state_lock"]`. `input_loop` reads from it under the same lock when printing status.

---

## 18. Worker Terminal Commands

Member 4 implements exactly these commands in `input_loop`. The strings are fixed so the demo script works consistently.

|User types|Action|
|---|---|
|`request`|Send `request_lock` to LM (only if not already in queue and not holding lock)|
|`release`|Send `release_lock` to LM (only if currently holding lock)|
|`status`|Print current clock value, queue, and who holds the lock|
|`quit`|If holding lock, release first. Then close socket and exit.|

Invalid commands print `Unknown command. Try: request, release, status, quit.` and continue the loop without crashing.

---

## 19. My IP Detection

Both `lock_server.py` (for registration) and `worker_client.py` (for logging) need to know the machine's LAN IP, not `127.0.0.1`. Use this exact utility, added to `utils.py` by Member 2:

```python
def get_local_ip() -> str:
    """
    Returns the machine's LAN IP address (e.g. 192.168.1.10).
    Falls back to 127.0.0.1 if detection fails.
    Does not send any real network traffic.
    """
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
```

### Resource Log File

The shared resource is represented by a single append-only log file defined in `config.py` as `RESOURCE_LOG_FILE = "resource_access.log"`. When a worker holds the lock, it writes to this file once per second for the duration it holds it.

**This file is the proof of mutual exclusion.** After the demo, the grader can open `resource_access.log` and verify that no two worker IDs appear interleaved — every block of lines belongs to exactly one worker before the next worker's lines begin.

Correct log (mutual exclusion working):

```
[12:00:01] [WA] USING gpu_0 tick=1
[12:00:02] [WA] USING gpu_0 tick=2
[12:00:03] [WA] USING gpu_0 tick=3
[12:00:04] [WB] USING gpu_0 tick=1
[12:00:05] [WB] USING gpu_0 tick=2
```

Broken log (what a race condition looks like — must never happen):

```
[12:00:01] [WA] USING gpu_0 tick=1
[12:00:01] [WB] USING gpu_0 tick=1   ← two workers at same time = failure
[12:00:02] [WA] USING gpu_0 tick=2
```

The lock hold duration for the demo should be set to 5 seconds (`simulate_resource_use` called with `duration_sec=5`). The max hold timeout in `config.py` is 30 seconds, giving workers enough time to use the resource before the watchdog fires.

---

## 20. Startup Sequence — Exact Timing Contract

This defines what "ready" means for each process, so members can write reliable startup logic.

|Process|"Ready" means|How others detect it|
|---|---|---|
|Naming Server|Bound to port and `accept()` loop is running|Prints `[NS][--] Naming Server ready on port 5000`|
|Lock Manager|Registered with NS AND bound to its own port AND `accept()` loop is running|Prints `[LM][CLOCK=1] Lock Server ready on port 9000`|
|Worker|Connected to LM AND `hello` acknowledged (no error received) AND listener thread started|Prints `[WA][CLOCK=1] Connected to Lock Manager. Ready.`|

No process should attempt to connect to another before that process has printed its ready line. During the demo, start each process and wait for the ready line before starting the next.

---

## 21. Test File Contracts

Members 1, 2, and 3 each deliver one test file. These run without a network — no sockets needed except Member 2's framing test which uses `socketpair`.

### `tests/test_clock.py` — Member 3 writes

```python
def test_initial_value():       # clock.value() == 0
def test_tick():                # clock.tick() returns 1, then 2
def test_send():                # clock.send() increments before returning
def test_receive_higher():      # receive(10) on clock=3 gives 11
def test_receive_lower():       # receive(1) on clock=5 gives 6
def test_receive_equal():       # receive(5) on clock=5 gives 6
def test_thread_safety():       # 100 threads each call tick() once; final value == 100
```

### `tests/test_framing.py` — Member 2 writes

```python
def test_roundtrip_simple():    # send then recv returns identical dict
def test_roundtrip_unicode():   # dict with unicode strings survives roundtrip
def test_roundtrip_large():     # dict with 10,000 char string survives roundtrip
def test_partial_recv():        # simulates recv returning data in small chunks; still works
```

### `tests/test_naming.py` — Member 1 writes

```python
def test_register_and_lookup(): # register a name, look it up, get correct IP/port
def test_lookup_missing():      # lookup a name that was never registered returns NOT_FOUND
def test_re_register():         # register same name twice with different port; lookup returns new port
def test_concurrent_requests(): # 10 threads register different names simultaneously; all resolve correctly
```

---

## 22. Git Workflow

```
main          ← protected. Only Member 5 merges into this after integration.
├── member1/naming-server
├── member2/utils-networking
├── member3/utils-clock
├── member4/worker-client
└── member5/lock-server
```

Merge order during integration:

```
1. member1/naming-server  → main   (CP-1 must pass)
2. member2/utils-networking → main  (CP-2 must pass)
3. member3/utils-clock → main       (CP-3 must pass)
4. member4/worker-client → main     (CP-4 must pass)
5. member5/lock-server → main       (CP-5 and CP-6 must pass)
```

No member merges their own branch. Member 5 reviews and merges all branches in the order above after the checkpoint for each one passes.

---

## 23. Report Structure and Ownership

### Section Ownership

| Report Section                            | Owner                        | Approximate length                      |
| ----------------------------------------- | ---------------------------- | --------------------------------------- |
| Title page, table of contents             | Member 5 (assembler)         | —                                       |
| 1. Introduction & project overview        | Member 5                     | 300–400 words                           |
| 2. System architecture & diagram          | Member 1                     | 300–400 words + diagram as embedded PNG |
| 3. Naming implementation                  | Member 1                     | 400–500 words                           |
| 4. Message-oriented communication         | Member 2                     | 400–500 words                           |
| 5. Lamport clock & synchronization        | Member 3                     | 400–500 words                           |
| 6. Individual reflections                 | Each member writes their own | minimum 200 words each                  |
| 7. Conclusion                             | Member 4                     | 200–300 words                           |
| Appendix: message schema                  | Member 2                     | paste from spec                         |
| Appendix: test results & log file excerpt | Member 5                     | paste from demo run                     |

### Assembly

Member 5 assembles the final DOCX. Each member submits their section as a plain `.txt` or `.docx` fragment by an agreed internal deadline (recommended: 48 hours before submission). Member 5 applies consistent formatting, embeds the architecture diagram PNG, pastes the appendices, and does a final proofread.

### Reflection Minimum (200 words each)

Each reflection must address all three of these points or it does not meet the minimum:

- What specific technical concept was hardest to understand and how did you resolve it
- What you would do differently if you rebuilt your component from scratch
- How your component depended on or was depended on by other members' work

---

## 24. Demo Script (new, assigned to Member 5)

Member 5 owns this script. Rehearse it at least once end-to-end before the presentation day.

```
[0:00] Start naming_server.py. Wait for ready line.
[0:30] Start lock_server.py. Wait for ready line. Show terminal: "Registered as lock.server.main."
[1:00] Start Worker A (terminal 3). Show lookup + connect.
[1:30] Start Worker B (terminal 4). Start Worker C (terminal 5).
[2:00] On Worker A: type "request". On Worker B: type "request". On Worker C: type "request".
       — All three hit enter as close to simultaneously as possible.
[2:15] Point to Lock Manager terminal. Show queue printout with Lamport order.
       Explain: "WA, WB, WC are sorted by (timestamp, worker_id). The winner is at position 0."
[2:30] Show Worker A terminal: "Lock granted." Show resource_access.log updating live (use: tail -f resource_access.log).
[3:00] Worker A: type "release". Show WB granted immediately. Show log file — no interleaving.
[3:30] Worker B: type "release". Worker C granted.
[4:00] Worker C: type "release". Queue empty. All workers show idle.
[4:30] LAMPORT DEMO: restart the demo. Before Worker B types "request", add time.sleep(2) live
       (or use a pre-prepared slow_worker.py). Show that despite the delay,
       if WB's Lamport timestamp is lower, WB still wins the queue.
[7:00] Show resource_access.log to professor. Point out clean non-interleaved blocks.
[8:00] CP-7 demo: open a 6th terminal, start Worker A again (duplicate ID).
       Show error message. Show original Worker A is unaffected.
[9:00] Questions buffer.
```
# DCRLM — Distributed Cloud Resource Lock Manager

A distributed mutual exclusion system built in Python using Lamport logical clocks. Three worker processes compete for exclusive access to a shared resource (`gpu_0`). A central Lock Manager enforces ordering. A Naming Server decouples workers from hardcoded addresses.

No external dependencies. Standard library only.

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white)
![stdlib](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-in%20development-yellow)

---

## How It Works

```
Worker A ──┐
Worker B ──┼──► Lock Manager ──► Naming Server
Worker C ──┘
```

1. The Naming Server starts first and listens for `REGISTER` and `LOOKUP` commands.
2. The Lock Manager registers itself with the Naming Server on startup.
3. Workers look up the Lock Manager's address via the Naming Server, then connect.
4. Workers send `request_lock` messages with a Lamport timestamp. The Lock Manager queues requests sorted by `(timestamp, worker_id)` and grants the lock to the front of the queue.
5. The current lock holder writes to `resource_access.log` once per second as proof of exclusive access.
6. On `release_lock`, the Lock Manager grants the lock to the next worker in the queue and broadcasts the update to all connected workers.
7. A watchdog thread in the Lock Manager auto-releases the lock after 30 seconds if the holder does not release it.

---

## Project Structure

```
dcrlm/
├── naming_server.py      Member 1 — REGISTER/LOOKUP registry
├── lock_server.py        Member 5 — mutual exclusion engine
├── worker_client.py      Member 4 — interactive worker process
├── utils.py              Members 2 & 3 — shared library (framing, clock, queue)
├── config.py             Global constants — do not modify without team agreement
├── requirements.txt      stdlib only — no pip installs needed
├── slow_worker.py        Member 5 — lag test variant of worker_client
└── tests/
    ├── test_clock.py     Member 3
    ├── test_framing.py   Member 2
    └── test_naming.py    Member 1
```

---

## Running the System

Start each process in a separate terminal. Wait for the ready line before starting the next.

**Terminal 1 — Naming Server**
```bash
python naming_server.py
# Ready: [NS][--] Naming Server ready on port 5000
```

**Terminal 2 — Lock Manager**
```bash
python lock_server.py
# Ready: [LM][CLOCK=1] Lock Server ready on port 9000
```

**Terminal 3, 4, 5 — Workers**
```bash
python worker_client.py --id WA
python worker_client.py --id WB
python worker_client.py --id WC
# Ready: [WA][CLOCK=1] Connected to Lock Manager. Ready.
```

---

## Worker Commands

Once a worker is running, type these commands in its terminal:

| Command   | Effect |
|-----------|--------|
| `request` | Request the lock (ignored if already in queue or holding lock) |
| `release` | Release the lock (ignored if not holding) |
| `status`  | Print current clock value, queue, and lock holder |
| `quit`    | Release lock if held, then disconnect and exit |

---

## Configuration

All tuneable values are in `config.py`. Do not hardcode values elsewhere.

| Constant | Default | Description |
|---|---|---|
| `NAMING_SERVER_HOST` | `127.0.0.1` | Change to LAN IP for multi-machine |
| `NAMING_SERVER_PORT` | `5000` | Naming Server listen port |
| `LOCK_SERVER_DEFAULT_PORT` | `9000` | Lock Manager listen port |
| `LOCK_MAX_HOLD_SEC` | `30` | Watchdog timeout in seconds |
| `SOCKET_TIMEOUT_SEC` | `5.0` | Blocking recv timeout |
| `RESOURCE_LOG_FILE` | `resource_access.log` | Mutual exclusion proof file |

**Multi-machine setup:** Set `NAMING_SERVER_HOST` to the LAN IP of the machine running the Naming Server. All other machines must use the same value.

---

## Running Tests

Tests require no network. Run from the project root:

```bash
python -m pytest tests/
```

Or individually:

```bash
python -m pytest tests/test_clock.py
python -m pytest tests/test_framing.py
python -m pytest tests/test_naming.py
```

All three test files must pass before any branch is merged into `main`.

---

## Verifying Mutual Exclusion

After running CP-5 (three workers simultaneously), open `resource_access.log`. Worker blocks must never interleave.

**Correct — mutual exclusion working:**
```
[12:00:01] [WA] USING gpu_0 tick=1
[12:00:02] [WA] USING gpu_0 tick=2
[12:00:03] [WA] USING gpu_0 tick=3
[12:00:04] [WB] USING gpu_0 tick=1
[12:00:05] [WB] USING gpu_0 tick=2
```

**Broken — race condition:**
```
[12:00:01] [WA] USING gpu_0 tick=1
[12:00:01] [WB] USING gpu_0 tick=1   ← two workers at same time
```

---

## Git Workflow

```
main                      ← protected, Member 5 merges only
├── member1/naming-server
├── member2/utils-networking
├── member3/utils-clock
├── member4/worker-client
└── member5/lock-server
```

No member merges their own branch. All merges go through a pull request reviewed by Member 5. Direct pushes to `main` are disabled.

Merge order is fixed by checkpoint dependencies:

```
member1/naming-server    → main   after CP-1
member2/utils-networking → main   after CP-2
member3/utils-clock      → main   after CP-3
member4/worker-client    → main   after CP-4
member5/lock-server      → main   after CP-5
```

---

## Team

| Member | Role | Files owned |
|---|---|---|
| Member 1 | Registry Architect | `naming_server.py`, `tests/test_naming.py` |
| Member 2 | Network Utilities | `utils.py` (framing half), `tests/test_framing.py` |
| Member 3 | Clock and Queue | `utils.py` (clock half), `tests/test_clock.py` |
| Member 4 | Client Developer | `worker_client.py` |
| Member 5 | Server Developer and Integrator | `lock_server.py`, `slow_worker.py`, report assembly, demo |
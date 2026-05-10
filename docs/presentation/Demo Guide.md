# Live demo guide

Assume all files are in one directory. Open **5 terminal windows** before you begin — one per process, plus one spare.

---

## Before you start

Make sure you know:

- Where `naming_server.py`, `lock_server.py`, and `worker_client.py` live
- What port the naming server uses (default: `5000`)
- The machine's local IP (run `ifconfig` or `hostname -I`)

---

## Step 1 — Start the naming server

**Terminal 1:**

```bash
python naming_server.py
```

**What to say:**

> "This is the naming server. It's the only process with a hardcoded port — everything else discovers each other through it. Think of it as DNS for our system. Right now it's empty — no services registered yet."

**Concept:** Location independence. Clients never hardcode the lock server's address. They ask the naming server for it. If the lock server moves or restarts, only it needs to re-register — workers are unaffected.

---

## Step 2 — Start the lock server

**Terminal 2:**

```bash
python lock_server.py
```

**What to say:**

> "The lock server starts up and immediately sends a REGISTER message to the naming server — announcing its address. From this point, workers can find it. The lock queue is empty, no one holds the lock."

**What to show:** Switch to Terminal 1. You should see the naming server log the registration: the name `lock.server.main` mapped to an `ip:port`.

**Concept:** Self-registration. The lock server doesn't wait to be configured — it announces itself. This is how distributed services decouple their physical location from their logical identity.

---

## Step 3 — Connect Worker 1

**Terminal 3:**

```bash
python worker_client.py --id W1
```

**What to say:**

> "Worker 1 starts. First it asks the naming server: 'where is lock.server.main?' The naming server replies with the address. Then Worker 1 opens a TCP connection to the lock server and sends a hello message to register its ID."

**Concept:** The naming lookup happens once at startup. After that, W1 talks directly to the lock server — the naming server is out of the picture.

---

## Step 4 — Connect Workers 2 and 3

**Terminal 4:**

```bash
python worker_client.py --id W2
```

**Terminal 5:**

```bash
python worker_client.py --id W3
```

**What to say:**

> "Same process for W2 and W3. Each does a LOOKUP, gets the address, connects. The lock server now has three open TCP connections — one thread per worker listening for messages."

**Concept:** The lock server's accept loop runs continuously. Each new connection spawns a dedicated thread. Shared state — the queue and lock holder — is protected by a mutex so these threads don't corrupt each other.

---

## Step 5 — First lock request (uncontested)

**In Terminal 3 (W1):** Request the lock.

**What to say:**

> "W1 requests the lock. It increments its Lamport clock, attaches the timestamp to the request, and sends it. The lock server receives it, applies Lamport Rule 3 to update its own clock, adds W1 to the queue, and since no one holds the lock, grants it immediately."

**What to show:** W1's terminal shows `lock granted`. W2 and W3 show a `queue_update` — they can see the queue even though they haven't requested yet.

**Concept:** Lamport Rule 3 — on receive, `clock = max(my_clock, incoming_timestamp) + 1`. The lock server's clock is now ahead of all workers'.

---

## Step 6 — Release the lock

**In Terminal 3 (W1):** Release the lock.

**What to say:**

> "W1 is done. It sends release_lock with its current Lamport timestamp. The lock server removes W1 from the queue. Queue is now empty, no one waiting, so no grant is sent."

---

## Step 7 — Contested requests (the interesting part)

**Quickly, in rapid succession — W1, W2, W3 all request the lock.**

**What to say:**

> "Now all three request at roughly the same time. This is the race. Each attaches its own Lamport timestamp. The lock server receives them — possibly in a different order than they were sent, because network timing is unpredictable. But it doesn't matter. The queue is sorted by (timestamp, worker_id), not by arrival order."

**What to show:** Point to the queue broadcast on W2 and W3's terminals. Show the sorted order.

**Concept:** This is the core of Lamport's mutual exclusion algorithm. Physical arrival order is irrelevant. Logical timestamp order is what determines fairness. If two timestamps tie, the lower worker ID wins — a deterministic tiebreak.

---

## Step 8 — Walk through the queue

Let the lock holder (say W1) release, then W2 gets it, then W3.

**What to say:**

> "Watch the queue drain in order. Each worker knows its position because the lock server broadcasts a queue_update after every grant and release. No worker is starved — the algorithm is fair by construction."

**Concept:** Fairness. Because timestamps reflect causal order and the queue is deterministic, every request is eventually served. No worker can be skipped.

---

## Step 9 — Simulate a crash (if time allows)

Kill one worker mid-queue with `Ctrl+C`.

**What to say:**

> "What happens if a worker disconnects without releasing the lock? The lock server detects the closed socket, removes that worker from the queue, and if it held the lock, releases it automatically. The system recovers."

**Concept:** Fault tolerance at the application layer. TCP doesn't guarantee the other side is still alive — the server must handle abrupt disconnects explicitly.

---

## Closing summary (30 seconds)

> "What you saw: three concepts working together. Lamport clocks gave us a consistent ordering of events without a shared clock. The naming server gave us location independence — no hardcoded addresses. And mutual exclusion via a sorted queue gave us fairness — one holder at a time, in a deterministic order. These are the building blocks of any real distributed coordination system."
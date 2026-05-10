# DCRLM — Speaker Script
### All 17 Slides · Exact Words + Recall Outline

---

## Slide 01 — Title
**Distributed Cloud Resource Lock Manager**

### Exact words
"Good [morning/afternoon]. Our project is called the Distributed Cloud Resource Lock Manager — DCRLM for short. What we built is a system that lets multiple worker machines compete for a shared resource, like a GPU or a database, in a way that is fair and safe even across a network where clocks disagree and messages arrive out of order. There are five of us, nine test checkpoints, and three core concepts that hold it all together. We'll walk through each one."

### Recall outline
- Name: DCRLM — distributed mutual exclusion
- The scenario: workers competing for one resource
- 3 concepts, 5 members, 9 checkpoints
- "We'll walk through each one"

---

## Slide 02 — The Problem
**Distributed systems break the rules we rely on**

### Exact words
"So why is this hard? On a single machine, you use a mutex — one line of code. But in a distributed system, three things break. First: no shared clock. Each machine has its own hardware clock that drifts, so you cannot trust timestamps from different computers. Second: no shared memory. Machines can't read each other's variables — everything must go through the network. Third: partial failures — one machine can crash while the others keep running, and the system has to handle that gracefully.

The core challenge is this: only one worker may use the resource at a time, but there is no mutex, no semaphore, no shared state. We have to build mutual exclusion entirely out of message passing."

### Recall outline
- Single machine: mutex = easy
- 3 problems: no shared clock, no shared memory, partial failures
- Core challenge: build a mutex with only message passing

---

## Slide 03 — Architecture: Three Processes
**Each process has exactly one job**

### Exact words
"Our system has exactly three kinds of processes. The Naming Server runs first. Its only job is to map logical service names to physical IP and port addresses — think of it as a miniature DNS. The only hardcoded value in the entire system is its port: 5000.

The Lock Manager is the central engine. It keeps the priority queue, grants and releases the lock, and broadcasts queue updates to everyone. It runs one thread per connected worker, and all shared state is protected by a mutex.

The Worker Client is what a user actually runs — an interactive terminal. It resolves the Lock Manager's address through the Naming Server, connects, and then runs two threads: one for user input, one listening for broadcasts from the server."

### Recall outline
- Naming Server: logical name → IP:port, port 5000 only hardcode
- Lock Manager: priority queue, grants/releases, one thread per worker
- Worker Client: terminal, two threads (input + listener)

---

## Slide 04 — Architecture: Startup Order
**Startup order is non-negotiable**

### Exact words
"The startup order matters and cannot be changed. First, the Naming Server — it has to be running before anything tries to register or look up an address. Second, the Lock Manager — it registers its dynamic port with the Naming Server so workers can find it. Third, the Workers — any number, in any order, each one does a LOOKUP at startup.

If you flip this order, the system fails before it begins. If a Worker starts before the Lock Manager registers, the lookup fails. If the Lock Manager starts before the Naming Server, registration fails. This is a hard dependency, not just a convention."

### Recall outline
- Order: Naming Server → Lock Manager → Workers (any order)
- Each step depends on the previous: lookup fails without registration
- Hard dependency, not convention

---

## Slide 05 — Integration: Message Flow
**End-to-end message flow**

### Exact words
"Here's the full lifecycle in six steps. One — Naming Server starts, binds port 5000, waits. Two — Lock Manager starts, sends REGISTER with its IP and port. Three — each Worker sends LOOKUP, gets the address back, opens a TCP connection, and sends a hello message to identify itself. Four — when a Worker wants the resource, it increments its Lamport clock and sends a request_lock message with its timestamp and ID. Five — the Lock Manager applies Lamport Rule 3, adds the request to the priority queue, sorts it, and grants the lock to whoever is at the front — sending queue_update to everyone else so they know their position. Six — when the Worker is done, it sends release_lock, the Lock Manager removes it, and grants the next one in line. The cycle repeats."

### Recall outline
- 6 steps: NS starts → LM registers → Workers resolve & connect → request → grant + broadcast → release
- Cycle repeats

---

## Slide 06 — Integration: Dependencies
**Build dependency chain & shared library**

### Exact words
"There's a strict build dependency chain. Member 1 — the Naming Server — must finish first. Nothing else can be integrated until that component passes standalone tests. Members 2 and 3 can then work in parallel — Member 2 owns the networking half of utils.py, Member 3 owns the clock half. Only after those are done can Members 4 and 5 fully integrate their components.

The glue between all five is utils.py. It contains two things: send_json and recv_json for TCP framing, and the LamportClock class. Every single process imports from this file. That's why the message schema must be agreed on in writing before anyone writes a line of code."

### Recall outline
- Chain: M1 first → M2 + M3 parallel → M4 + M5 integrate
- utils.py is the shared glue: send/recv JSON + LamportClock
- Schema agreement comes before any code

---

## Slide 07 — Naming Server
**Decoupling identity from address**

### Exact words
"Let's go deeper on each concept. Concept one: the Naming Server. The problem with hardcoding an IP like 192.168.1.45 colon 9000 into every worker is that if the Lock Manager restarts on a different port, every client breaks. The naming server decouples the logical name from the physical location. The registry just maps the name 'lock.server.main' to a tuple of IP and port.

The protocol is simple. The Lock Manager calls REGISTER on startup with its address. Every Worker calls LOOKUP to get that address. After that first lookup, workers connect directly to the Lock Manager — the Naming Server is not contacted again during the session. Port 5000 is the only thing that has to be known in advance."

### Recall outline
- Problem: hardcoded IPs break on restart
- Solution: registry maps logical name → IP:port
- Protocol: REGISTER (LM) → LOOKUP (Worker) → done
- NS not used again after startup; port 5000 only hardcode

---

## Slide 08 — Message Communication
**JSON over TCP with length framing**

### Exact words
"Concept two: message-oriented communication. Every interaction between processes is a discrete JSON message with a type field. Workers send request_lock, release_lock, hello. The Lock Manager broadcasts lock_granted and queue_update. This makes the protocol human-readable and easy to debug.

But there's a problem with TCP: it's a byte stream, not a message protocol. If you call recv with 4096 bytes, you might get half a JSON object, or two objects merged together. Our fix is a length-prefix scheme. Every message is sent as 4 bytes encoding the payload length, followed by the payload. recv_json reads exactly 4 bytes first, unpacks the length, then reads exactly that many bytes. This works regardless of how TCP fragments the data.

And workers use two threads — one for user input, one listening for server broadcasts — so sending and receiving are decoupled in time."

### Recall outline
- All messages are typed JSON
- TCP problem: stream, not messages — can split or merge
- Fix: 4-byte length prefix → read N bytes exactly
- Workers: two threads, sender + listener decoupled

---

## Slide 09 — Lamport Clocks
**Three rules that order events without a shared clock**

### Exact words
"Concept three: Lamport logical clocks. This is the heart of fairness in the system. A Lamport clock is not a real clock — it's an integer counter. Three rules govern it. Rule 1: before any local event, increment your clock. Rule 2: before sending a message, increment your clock and attach the value to the message. Rule 3 — the key one: when you receive a message with timestamp T, set your clock to the max of your current clock and T, then add one.

This guarantees that if event A causally preceded event B — meaning A's message was the reason B happened — then A's timestamp will always be strictly less than B's. And when two events have equal timestamps because they happened on different machines with no causal link, we break the tie by worker ID alphabetically. 'WA' beats 'WB' beats 'WC' — deterministic and fair.

Look at the example on the right. WA and WB both send a request at timestamp 3. WA's message arrived second at the server — but it still wins, because 'WA' is alphabetically less than 'WB'. Physical arrival order is irrelevant. Logical order is what matters."

### Recall outline
- Lamport clock = integer counter, not a real clock
- 3 rules: local event +1 / send: +1 attach / receive: max(clock, T)+1
- Guarantees causal order
- Tie-break: alphabetical worker ID
- Example: WA arrives second but wins — logical over physical

---

## Slide 10 — Build Plan: Phases 1–2
**Phases 1 & 2 — Setup and parallel build**

### Exact words
"Here's how we structure the build. Phase 1 is sequential and done by everyone together: read the spec, resolve the eight open design decisions, set up the GitHub repo, and create the project skeleton. The most important output of Phase 1 is the agreed JSON message schema in writing — because Members 2, 4, and 5 all depend on it.

Phase 2 is fully parallel. All five members work independently at the same time. Member 1 builds the Naming Server. Member 2 writes send_json and recv_json with a minimal echo server test. Member 3 writes the LamportClock class and tests it with two simulated nodes. Members 4 and 5 can start with stubs — the file structure just needs to be in place.

The critical blocker: Member 1 must finish and pass standalone tests before Members 4 and 5 can do any real integration."

### Recall outline
- Phase 1: sequential — schema, repo, skeleton, everyone aligned
- Phase 2: fully parallel — each member owns one component, stubs are fine
- Critical blocker: M1 must pass standalone before M4/M5 integrate

---

## Slide 11 — Build Plan: Phases 3–5
**Phases 3–5 — Wire, test, deliver**

### Exact words
"Phase 3 is integration. The foundation components — naming, framing, clock — are verified against checkpoints CP-1 through CP-3 in sequence. Then Members 4 and 5 integrate in parallel: Member 5 builds the Lock Manager skeleton accepting connections, Member 4 builds the Worker connecting through the naming server. Member 3 then integrates the clock into both.

Phase 4 is testing under real conditions: nine checkpoints from a single-worker smoke test up to a five-worker stress test and a simulated network lag test. All nine must pass.

Phase 5 is delivery: report writing in parallel, DOCX assembly, and a demo rehearsal. The system was built with five parallel contributors, one shared spec, zero pip installs — stdlib only — and nine checkpoints standing between us and submission."

### Recall outline
- Phase 3: sequential CPs (naming/framing/clock) then parallel integration (M4+M5)
- Phase 4: 9 checkpoints — smoke test → stress test → lag test
- Phase 5: report, DOCX, demo rehearsal
- Key stats: 5 parallel, 9 CPs, 1 spec, 0 pip installs

---

## Slide 12 — Team: Members 1–3
**Members 1–3: Foundation layer**

### Exact words
"Quick look at the team. Members 1, 2, and 3 own the foundation layer. Member 1 — the Registry Architect — owns naming_server.py and its tests. Their deliverable must come first because it blocks everyone else. Member 2 — the Middleware Engineer — owns the networking half of utils.py: send_json, recv_json, message framing. Member 3 — the Timekeeper — owns the clock half: the LamportClock class, the queue sort logic, and the grant and release decision logic inside the Lock Manager.

The dependency note: M2 and M3 can work in parallel, but Members 4 and 5 cannot fully integrate until all three foundation components are done and tested."

### Recall outline
- M1: Registry Architect — naming_server.py — first blocker
- M2: Middleware Engineer — utils.py networking — send/recv + framing
- M3: Timekeeper — utils.py clock + queue logic
- M4 and M5 blocked until all three done

---

## Slide 13 — Team: Members 4–5
**Members 4–5: Application layer**

### Exact words
"Members 4 and 5 own the application layer — the parts the user actually interacts with and the part that integrates everything. Member 4 — the Client Developer — builds worker_client.py: the terminal UI, the listener thread, and clock integration on the client side, including handling duplicate worker IDs. Member 5 — the Server Developer and Integrator — builds lock_server.py, the accept loop, the per-worker threads, and is responsible for integrating all components together. Member 5 also leads system testing from checkpoint CP-4 through CP-9 and assembles the final DOCX report.

Shared by all members: config.py, which is the single source of truth for ports, timeouts, and constants. No one modifies it without team agreement."

### Recall outline
- M4: Client Developer — worker_client.py — UI, listener thread, clock, duplicate ID
- M5: Server Developer & Integrator — lock_server.py — accept loop, threads, integrates all, leads testing
- config.py: shared, single source of truth, no unilateral changes

---

## Slide 14 — Summary
**Three concepts. One working system.**

### Exact words
"To summarize. Three concepts working together make this system work. The Naming Server gives us location independence through DNS-style resolution — logical names decouple identity from address. TCP with length-prefix framing gives us reliable message-oriented communication that handles TCP's stream nature correctly. And Lamport clocks give us causal ordering without a shared clock — a priority queue with tie-breaking by ID that is fair, deterministic, and has no starvation.

The key property of the whole system: exactly one worker holds the lock at any moment, regardless of network timing, physical arrival order, or clock drift — enforced entirely through message passing."

### Recall outline
- 3 pillars: Naming (DNS-style) / TCP framing (length prefix) / Lamport (causal order)
- Key property: exactly one holder at any moment, enforced by message passing only
- No starvation, deterministic, fair

---

## Slide 15 — Submission Package
**Submission package**

### Exact words
"Here's what we're delivering. Five Python files: naming_server, lock_server, worker_client, utils, and config. A tests directory. A demo resource access log. And the final report as a DOCX.

Everything runs on Python's standard library — no pip installs. We use socket, threading, json, struct, and queue. Nine checkpoints must all pass, from a single-worker smoke test to a five-worker stress test. The build was structured across five parallel contributors following one shared specification, with AI pair programming to accelerate the work."

### Recall outline
- Files: 5 .py files, tests/, log file, DOCX report
- stdlib only: socket, threading, json, struct, queue — zero pip
- 9 checkpoints all must pass
- 5 parallel contributors, 1 spec, AI-assisted

---

## Slide 16 — Next Steps: Phases 1–3
**Phases 1–3: Agree, build, integrate**

### Exact words
"Here's what happens immediately after this presentation. Phase 1 — today — everyone agrees on the complete JSON message schema and writes it down in a shared doc. We create the GitHub repository and agree on a branching strategy. Member 1 starts on naming_server.py immediately — it is the blocker.

Phase 2 — parallel build. Member 1 finishes and verifies the Naming Server from a raw terminal. Member 2 tests send and recv with a minimal echo server. Member 3 tests the Lamport clock with two simulated nodes.

Phase 3 — wiring. Member 5 builds the Lock Manager skeleton that accepts connections and echoes messages. Member 4 connects through the Naming Server and sends a hello. Member 3 then integrates the clock into both lock_server and worker_client."

### Recall outline
- Phase 1 (today): schema in writing, repo up, M1 starts immediately
- Phase 2 (parallel): each member tests their component standalone
- Phase 3: M5 skeleton → M4 connects → M3 integrates clock

---

## Slide 17 — Next Steps: Phases 4–5
**Phases 4–5: Test under real conditions & deliver**

### Exact words
"Phase 4 is testing under real conditions. First, all three programs on separate terminal windows on one machine. Then on separate laptops on the same Wi-Fi — that's where real distributed issues appear. We add a two-second sleep in one Worker's send path to simulate network lag, and verify the Lamport-ordered queue still grants the lock in the correct logical order despite the delay. We record that test for the demo. Then the stress test: five workers simultaneously, all requesting the lock at once. The system must not crash and must grant to exactly one at a time.

Phase 5 is the final deliverable. Source code with comments explaining why, not just what — the grader reads comments. Architecture diagrams. The DOCX report: introduction, one section per pillar, one reflection per member. And we rehearse the live demo at least once before the presentation. Know the startup order cold. If one laptop fails, the whole system can run on one machine with three terminals.

Thank you."

### Recall outline
- Phase 4: one machine first → laptops on Wi-Fi → lag simulation (sleep 2) → 5-worker stress test
- Record lag test for demo
- Phase 5: comments explain WHY / DOCX report: 1 section per pillar, 1 reflection per member
- Rehearse demo — know startup order — backup: single machine, 3 terminals
- End: "Thank you"
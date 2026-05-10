# Git Workflow Cheatsheet

---

## One-Time Setup (Each Member)

```bash
git clone <repo-url>
cd dcrlm
git checkout master
git pull origin master
git checkout member1/naming-server   # use your own branch name
```

---

## Daily Work Loop (Phase 2 — Working in Isolation)

Work only on your own branch. Do not touch other members' files.

```bash
# Start of each session — sync master in case skeleton was updated
git checkout master
git pull origin master
git checkout member1/naming-server
git merge master   # bring in any updates from master

# During work
git status
git add naming_server.py
git commit -m "feat(naming): implement handle_register"

# End of session — push your branch
git push origin member1/naming-server
```

---

## Commit Message Format

```
feat(naming): implement handle_register
feat(utils): add send_json and recv_json framing
feat(clock): implement LamportClock increment and update
feat(client): add send_request stub
feat(server): add process_request stub
fix(clock): correct max() call in update()
test(framing): add recv_json round-trip test
chore: update config.py with agreed port values
```

---

## Submitting Work via Pull Request (Phase 2 → Phase 3 Checkpoints)

When your Phase 2 tasks are done:

```bash
git push origin member1/naming-server
```

Then on GitHub:

- Open a Pull Request from `member1/naming-server` → `master`
- Title: `[CP-1] Naming server complete`
- Assign Member 5 as reviewer
- Do not merge yourself — Member 5 merges after review

---

## Checkpoint Merge (Member 5 Only)

After reviewing a PR:

```bash
# On GitHub — approve and merge via pull request UI
# Then locally
git checkout master
git pull origin master
```

---

## Keeping Your Branch Current (Phase 3 — Integration)

After CP-1, CP-2, or CP-3 merges into master, Members 4 and 5 must pull those changes before integrating.

```bash
git checkout master
git pull origin master
git checkout member4/worker-client
git merge master
# Resolve any conflicts, then:
git add .
git commit -m "chore: merge master after CP-1 naming server landed"
git push origin member4/worker-client
```

---

## Resolving a Merge Conflict

```bash
# After running git merge master and seeing conflicts:
git status                    # shows conflicted files
# Open the conflicted file — look for <<<<<<< markers
# Edit to keep the correct version
git add utils.py              # mark as resolved
git commit -m "fix: resolve merge conflict in utils.py"
```

---

## Phase 4 — Testing Hotfixes

If Member 5 finds a bug in another member's code during CP-4 through CP-9:

**Bug owner (e.g., Member 3):**

```bash
git checkout member3/utils-clock
# Fix the bug
git add utils.py
git commit -m "fix(clock): handle update() when incoming timestamp equals local"
git push origin member3/utils-clock
# Open a PR into master titled [HOTFIX] <description>
```

**Member 5:**

```bash
# Merges the hotfix PR, then:
git checkout master
git pull origin master
# Rerun the failing checkpoint
```

---

## Config-Only Temporary Change (CP-8 Watchdog Test)

Do not commit temporary test changes. Use this pattern:

```bash
# Make the temporary change to config.py locally
# Run CP-8 test
# Then revert before committing:
git checkout -- config.py
```

---

## Final Assembly (Phase 5 — Member 5)

```bash
git checkout master
git pull origin master
# Verify all member branches are merged
git log --oneline --graph --all

# After report and demo assets are added:
git add DCRLM_Final_Report.docx architecture_diagram.png demo_resource_access.log
git commit -m "chore: add final report, diagram, and demo log"
git push origin master
```

---

## Tagging the Final Submission

```bash
git tag -a v1.0 -m "Final submission — DCRLM"
git push origin v1.0
```

---

## Useful Inspection Commands

```bash
# See what changed before staging
git diff

# See what is staged
git diff --staged

# Check branch history
git log --oneline -10

# See all branches
git branch -a

# See who last changed each line of a file
git blame utils.py

# Undo last commit but keep changes staged
git reset --soft HEAD~1

# Discard all uncommitted changes to a file
git checkout -- filename.py
```

---

## Branch Reference

|Branch|Owner|Purpose|
|---|---|---|
|`master`|Member 5 (protected)|Integration target — no direct pushes|
|`member1/naming-server`|Member 1|naming_server.py|
|`member2/utils-networking`|Member 2|utils.py networking half|
|`member3/utils-clock`|Member 3|utils.py clock half|
|`member4/worker-client`|Member 4|worker_client.py|
|`member5/lock-server`|Member 5|lock_server.py|
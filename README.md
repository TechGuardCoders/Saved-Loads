# Saved Loads

Versioned checkpoint save/restore with integrity checks. Periodic snapshots of job state so a crashed 3-hour job resumes from minute 47, not zero.

## What it does

- `save(job_id, state)` → versioned snapshot dir (`v0001`, `v0002`, …) with a sha256 checksum of the payload
- `load(job_id)` → latest **valid** state; corrupt snapshots are skipped and the previous version is used
- `prune()` → keeps only the newest `max_versions` snapshots (default 5)
- `list(job_id)` → versions with timestamps and validity flags

## Architecture

```
<base_dir>/<job_id>/v0001/
    state.json      # {"schema": "saved-loads/v1", "job_id": ..., "state": ...}
    state.sha256    # sha256 hex of state.json bytes
```

Writes are atomic (temp file + rename). On load, the checksum is re-verified against the payload bytes; a mismatch (truncated write, bit rot, manual edit) marks the snapshot invalid and `load()` walks back to the newest valid one.

## Why

Long jobs die. Naive checkpointing has two failure modes: a single `state.pkl` that gets corrupted mid-write (you lose everything), and unbounded snapshot dirs that fill the disk. Saved Loads fixes both: every snapshot is checksummed so corruption is detected, not trusted, and pruning bounds storage while keeping a fallback chain.

## Usage

```python
from saved_loads import SavedLoads

sl = SavedLoads("./checkpoints", max_versions=5)

# every N steps of a long job
sl.save("train-run-7", {"step": 2820, "loss": 0.42, "rng": 12345})

# after a crash: newest valid snapshot, or None if none survive
state = sl.load("train-run-7")

for v in sl.list("train-run-7"):
    print(v["version"], v["saved_at"], v["valid"])
```

## Results

- 10 tests, all passing, no network required
- Corrupt-newest → falls back to previous version (tested)
- Checksum mismatch → snapshot rejected (tested)
- Prune keeps exactly `max_versions` (tested)

## CI

GitHub Actions runs `pytest -q` on push/PR. Badge:

[![CI](https://github.com/TechGuardCoders/Saved-Loads/actions/workflows/ci.yml/badge.svg)](https://github.com/TechGuardCoders/Saved-Loads/actions/workflows/ci.yml)

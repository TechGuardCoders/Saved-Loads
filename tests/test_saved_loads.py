import json
import os

import pytest

from saved_loads import SavedLoads


def test_save_and_load_roundtrip(tmp_path):
    sl = SavedLoads(str(tmp_path), max_versions=5)
    v = sl.save("job-a", {"step": 47, "loss": 0.42})
    assert v == 1
    assert sl.load("job-a") == {"step": 47, "loss": 0.42}


def test_versions_increment(tmp_path):
    sl = SavedLoads(str(tmp_path))
    assert sl.save("j", {"n": 1}) == 1
    assert sl.save("j", {"n": 2}) == 2
    assert sl.load("j") == {"n": 2}


def test_load_skips_corrupt_falls_back(tmp_path):
    sl = SavedLoads(str(tmp_path))
    sl.save("j", {"n": 1})
    v2 = sl.save("j", {"n": 2})
    # corrupt the newest snapshot
    with open(os.path.join(str(tmp_path), "j", f"v{v2:04d}", "state.json"), "w") as f:
        f.write('{"schema": "saved-loads/v1", "job_id": "j", "state": {"n": 999}}')
    assert sl.load("j") == {"n": 1}


def test_checksum_mismatch_rejected(tmp_path):
    sl = SavedLoads(str(tmp_path))
    sl.save("j", {"n": 1})
    vdir = os.path.join(str(tmp_path), "j", "v0001")
    with open(os.path.join(vdir, "state.json"), "r+b") as f:
        f.seek(-1, os.SEEK_END)
        f.write(b"X")
    assert sl.load("j") is None


def test_prune_keeps_max_versions(tmp_path):
    sl = SavedLoads(str(tmp_path), max_versions=3)
    for i in range(6):
        sl.save("j", {"n": i})
    versions = [v["version"] for v in sl.list("j")]
    assert versions == [4, 5, 6]
    assert sl.load("j") == {"n": 5}


def test_list_reports_validity_and_timestamp(tmp_path):
    sl = SavedLoads(str(tmp_path))
    sl.save("j", {"n": 1})
    entries = sl.list("j")
    assert len(entries) == 1
    assert entries[0]["valid"] is True
    assert entries[0]["saved_at"] is not None


def test_jobs_are_isolated(tmp_path):
    sl = SavedLoads(str(tmp_path))
    sl.save("a", {"who": "a"})
    sl.save("b", {"who": "b"})
    assert sl.load("a") == {"who": "a"}
    assert sl.load("b") == {"who": "b"}


def test_load_missing_job_returns_none(tmp_path):
    sl = SavedLoads(str(tmp_path))
    assert sl.load("nope") is None


def test_invalid_max_versions_raises(tmp_path):
    with pytest.raises(ValueError):
        SavedLoads(str(tmp_path), max_versions=0)


def test_checksum_file_matches_sha256_of_payload(tmp_path):
    import hashlib

    sl = SavedLoads(str(tmp_path))
    sl.save("j", {"n": 1})
    vdir = os.path.join(str(tmp_path), "j", "v0001")
    with open(os.path.join(vdir, "state.json"), "rb") as f:
        data = f.read()
    with open(os.path.join(vdir, "state.sha256")) as f:
        expected = f.read().strip()
    assert hashlib.sha256(data).hexdigest() == expected
    payload = json.loads(data)
    assert payload["schema"] == "saved-loads/v1"
    assert payload["job_id"] == "j"

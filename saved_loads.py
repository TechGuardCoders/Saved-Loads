"""Saved Loads — versioned checkpoint save/restore with integrity checks.

Periodic snapshots of job state so a crashed 3-hour job resumes from
minute 47, not zero. Pure Python, stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SCHEMA = "saved-loads/v1"


class SavedLoads:
    """Versioned checkpoint store.

    Layout under ``base_dir``::

        <base_dir>/<job_id>/v0001/
            state.json     # {"schema": ..., "job_id": ..., "state": ...}
            state.sha256   # sha256 hex of state.json bytes
    """

    def __init__(self, base_dir: str, max_versions: int = 5):
        if max_versions < 1:
            raise ValueError("max_versions must be >= 1")
        self.base_dir = base_dir
        self.max_versions = max_versions
        os.makedirs(base_dir, exist_ok=True)

    # -- paths ------------------------------------------------------------

    def _job_dir(self, job_id: str) -> str:
        return os.path.join(self.base_dir, job_id)

    def _version_dir(self, job_id: str, version: int) -> str:
        return os.path.join(self._job_dir(job_id), f"v{version:04d}")

    def _state_path(self, job_id: str, version: int) -> str:
        return os.path.join(self._version_dir(job_id, version), "state.json")

    def _checksum_path(self, job_id: str, version: int) -> str:
        return os.path.join(self._version_dir(job_id, version), "state.sha256")

    # -- core API ----------------------------------------------------------

    def save(self, job_id: str, state: Dict[str, Any]) -> int:
        """Write a new versioned snapshot; returns the version number."""
        versions = self._existing_versions(job_id)
        version = (max(versions) + 1) if versions else 1
        vdir = self._version_dir(job_id, version)
        os.makedirs(vdir, exist_ok=True)

        payload = {
            "schema": _SCHEMA,
            "job_id": job_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "state": state,
        }
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()

        # atomic-ish write: temp file then rename
        fd, tmp = tempfile.mkstemp(dir=vdir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, self._state_path(job_id, version))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        with open(self._checksum_path(job_id, version), "w", encoding="utf-8") as f:
            f.write(digest)

        self.prune(job_id)
        return version

    def load(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Latest valid state; skips corrupt snapshots, falls back to previous."""
        for version in sorted(self._existing_versions(job_id), reverse=True):
            state = self._load_version(job_id, version)
            if state is not None:
                return state
        return None

    def list(self, job_id: str) -> List[Dict[str, Any]]:
        """Versions with timestamps, oldest first. Corrupt ones flagged."""
        out = []
        for version in sorted(self._existing_versions(job_id)):
            saved_at = None
            valid = self._load_version(job_id, version) is not None
            try:
                with open(self._state_path(job_id, version), "rb") as f:
                    saved_at = json.loads(f.read().decode("utf-8")).get("saved_at")
            except (OSError, ValueError):
                pass
            out.append({"version": version, "saved_at": saved_at, "valid": valid})
        return out

    def prune(self, job_id: str) -> None:
        """Keep only the newest max_versions snapshots."""
        versions = self._existing_versions(job_id)
        for version in versions[: -self.max_versions] if len(versions) > self.max_versions else []:
            shutil.rmtree(self._version_dir(job_id, version), ignore_errors=True)

    # -- internals ---------------------------------------------------------

    def _existing_versions(self, job_id: str) -> List[int]:
        job_dir = self._job_dir(job_id)
        if not os.path.isdir(job_dir):
            return []
        out = []
        for name in os.listdir(job_dir):
            if name.startswith("v") and name[1:].isdigit():
                out.append(int(name[1:]))
        return sorted(out)

    def _load_version(self, job_id: str, version: int) -> Optional[Dict[str, Any]]:
        state_path = self._state_path(job_id, version)
        checksum_path = self._checksum_path(job_id, version)
        try:
            with open(state_path, "rb") as f:
                data = f.read()
            with open(checksum_path, "r", encoding="utf-8") as f:
                expected = f.read().strip()
        except OSError:
            return None
        if hashlib.sha256(data).hexdigest() != expected:
            return None
        try:
            payload = json.loads(data.decode("utf-8"))
        except ValueError:
            return None
        if payload.get("schema") != _SCHEMA or payload.get("job_id") != job_id:
            return None
        return payload.get("state")

"""Local user-profile persistence matching ai-server's favorability side channel."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


class UserProfileStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get(self, user_id: str) -> dict:
        path = self._path(user_id)
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def update(self, user_id: str, update: dict | None) -> dict:
        if not update:
            return self.get(user_id)
        profile = self.get(user_id)
        profile.update({key: value for key, value in update.items() if value})
        profile["last_updated"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        path = self._path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return profile

    def _path(self, user_id: str) -> Path:
        if not user_id or any(value in user_id for value in ("/", "\\", "..")):
            raise ValueError("Invalid user id")
        return self.directory / f"{user_id}.json"

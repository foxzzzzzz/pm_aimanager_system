from __future__ import annotations

import uuid
from pathlib import Path


class LocalImportStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, filename: str, content: bytes) -> tuple[str, Path]:
        self.root.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower()
        object_key = f"{uuid.uuid4().hex}{suffix}"
        target = self.root / object_key
        target.write_bytes(content)
        return object_key, target

    def delete(self, object_key: str) -> None:
        (self.root / object_key).unlink(missing_ok=True)

    def release(self, _path: Path) -> None:
        return None

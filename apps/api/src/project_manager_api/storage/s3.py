from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]


class S3ImportStorage:
    def __init__(
        self,
        endpoint: str,
        bucket: str,
        region: str,
        staging_root: Path,
        access_key: str | None,
        secret_key: str | None,
    ) -> None:
        self.bucket = bucket
        self.staging_root = staging_root
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._bucket_ready = False

    def put(self, filename: str, content: bytes) -> tuple[str, Path]:
        self._ensure_bucket()
        suffix = Path(filename).suffix.lower()
        object_key = f"imports/{uuid.uuid4().hex}{suffix}"
        self.staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=self.staging_root, suffix=suffix, delete=False
        ) as staged:
            staged.write(content)
            staged_path = Path(staged.name)
        try:
            self.client.upload_file(str(staged_path), self.bucket, object_key)
        except Exception:
            staged_path.unlink(missing_ok=True)
            raise
        return object_key, staged_path

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def release(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=self.bucket)
        self._bucket_ready = True

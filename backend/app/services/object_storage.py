"""Local upload storage with optional private S3 persistence.

S3 URIs are stored in dataset manifests. A task downloads each object into its
own scratch directory, so no shared ECS volume or public bucket is required.
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from ..config import settings


@lru_cache(maxsize=1)
def _s3():
    import boto3

    return boto3.client("s3")


def is_s3_uri(value: str | Path) -> bool:
    return str(value).startswith("s3://")


def _parts(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Invalid S3 object URI")
    return parsed.netloc, parsed.path.lstrip("/")


def persist_file(path: str | Path, *, prefix: str = "datasets") -> str:
    source = Path(path)
    if not settings.upload_bucket:
        return str(source)
    key = f"{prefix}/{source.name}"
    _s3().upload_file(str(source), settings.upload_bucket, key)
    return f"s3://{settings.upload_bucket}/{key}"


def materialize(uri: str | Path) -> Path:
    if not is_s3_uri(uri):
        return Path(uri)
    bucket, key = _parts(str(uri))
    digest = hashlib.sha256(str(uri).encode()).hexdigest()[:20]
    target = settings.upload_dir / "cache" / f"{digest}-{Path(key).name}"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + f".{uuid4().hex}.partial")
        _s3().download_file(bucket, key, str(temporary))
        temporary.replace(target)
    return target


def read_logo(name: str) -> bytes:
    if Path(name).name != name or not name.startswith(("logo-", "brand-")):
        raise ValueError("Invalid logo name")
    if settings.upload_bucket:
        return _s3().get_object(Bucket=settings.upload_bucket, Key=f"logos/{name}")["Body"].read()
    return (settings.upload_dir / name).read_bytes()

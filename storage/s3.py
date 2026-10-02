"""
Thin boto3 wrapper for the Raw layer bucket (Incus storage bucket, S3 API).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from config import RAW_BUCKET, S3_CA_BUNDLE, S3_ENDPOINT, S3_RAW_KEY, S3_RAW_SECRET

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def client():
    """Return a cached S3 client for the Incus bucket endpoint (path-style)."""
    if not S3_ENDPOINT:
        raise RuntimeError("HYDROC_S3_ENDPOINT is not set (see .env.example).")
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_RAW_KEY,
        aws_secret_access_key=S3_RAW_SECRET,
        region_name="us-east-1",
        verify=S3_CA_BUNDLE if S3_CA_BUNDLE else True,
        config=Config(s3={"addressing_style": "path"}),
    )


def put_file(local_path: Path, key: str, bucket: str = RAW_BUCKET) -> None:
    client().upload_file(str(local_path), bucket, key)
    logger.info("Uploaded %s -> s3://%s/%s", local_path.name, bucket, key)


def put_bytes(data: bytes, key: str, bucket: str = RAW_BUCKET) -> None:
    client().put_object(Bucket=bucket, Key=key, Body=data)
    logger.info("Wrote s3://%s/%s (%.1f KB)", bucket, key, len(data) / 1024)


def get_bytes(key: str, bucket: str = RAW_BUCKET) -> bytes:
    return client().get_object(Bucket=bucket, Key=key)["Body"].read()


def list_keys(prefix: str, bucket: str = RAW_BUCKET) -> list[str]:
    """Return every key under *prefix*, sorted."""
    keys: list[str] = []
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return sorted(keys)

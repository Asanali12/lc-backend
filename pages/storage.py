"""Tiny wrapper over Django's default_storage so the views don't have to know
whether they're writing to local disk or S3."""
from __future__ import annotations

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def _prefix() -> str:
    if settings.AWS_BUCKET and settings.LC_S3_PREFIX:
        return settings.LC_S3_PREFIX.rstrip("/") + "/"
    return "lc-pages/"


def html_key(page_id: str) -> str:
    return f"{_prefix()}{page_id}/html"


def events_key(page_id: str) -> str:
    return f"{_prefix()}{page_id}/events.json"


def state_key(page_id: str) -> str:
    """Editor doc-tree blob — lets the editor reopen a saved page losslessly.
    Optional: pages saved before this blob existed have no state.json and
    the raw_state view returns 404 for them."""
    return f"{_prefix()}{page_id}/state.json"


def blob_exists(key: str) -> bool:
    return default_storage.exists(key)


def write_blob(key: str, body: str) -> int:
    """Write a string blob to storage. Overwrites if the key exists."""
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(body.encode("utf-8")))
    return len(body.encode("utf-8"))


def read_blob(key: str) -> bytes:
    with default_storage.open(key, "rb") as fh:
        return fh.read()


def delete_blob(key: str) -> None:
    if default_storage.exists(key):
        default_storage.delete(key)

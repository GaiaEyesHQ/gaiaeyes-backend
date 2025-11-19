import mimetypes
import os
from typing import Optional

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BUCKET = os.getenv("BUCKET", "space-visuals")


class SupabaseUploadError(Exception):
    pass


def _public_url(path_key: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path_key.lstrip('/')}"


def upload_bytes(
    path_key: str,
    data: bytes,
    content_type: Optional[str] = None,
    cache_control: str = "public, max-age=300",
) -> str:
    if not SUPABASE_URL or not SERVICE_KEY:
        raise SupabaseUploadError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    if not content_type:
        content_type = mimetypes.guess_type(path_key)[0] or "application/octet-stream"
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path_key.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "true",
        "cache-control": cache_control,
    }
    resp = requests.post(url, headers=headers, data=data, timeout=60)
    if not (200 <= resp.status_code < 300):
        raise SupabaseUploadError(f"Upload failed {resp.status_code}: {resp.text[:200]}")
    return _public_url(path_key)


def upload_alias(latest_key: str, source_public_url: str, content_type: Optional[str] = None) -> str:
    r = requests.get(source_public_url, timeout=60)
    r.raise_for_status()
    return upload_bytes(latest_key, r.content, content_type=content_type)

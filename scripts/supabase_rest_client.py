import os
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def supabase_upsert(table, rows, on_conflict=None):
    """
    Upsert rows into a Supabase table using the REST API.
    No-op if SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing or rows is empty.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not rows:
        return

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url = f"{url}?on_conflict={on_conflict}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    # Prefer merge-duplicates for upsert
    if on_conflict:
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    else:
        headers["Prefer"] = "return=minimal"

    data = json.dumps(rows).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            _ = resp.read()
    except HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        print(f"[supabase_upsert] HTTP {e.code} for table={table}: {body}", flush=True)
    except URLError as e:
        print(f"[supabase_upsert] URL error for table={table}: {e}", flush=True)

def supabase_upsert(table, rows, on_conflict=None):
    """
    Upsert rows into a Supabase table via the REST API.
    Supports "table" (public schema) or "schema.table" (e.g., "ext.global_hazards").
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not rows:
        return

    # Parse schema.table if provided
    schema = "public"
    table_name = table
    if "." in table:
        parts = table.split(".", 1)
        if len(parts) == 2:
            schema, table_name = parts[0], parts[1]

    # Build REST URL (Supabase: always /rest/v1/{table_name})
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    if on_conflict:
        url = f"{url}?on_conflict={on_conflict}"

    # Headers for Supabase schema-targeting
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    # Non-public schema requires Content-Profile and Accept-Profile
    if schema != "public":
        headers["Content-Profile"] = schema
        headers["Accept-Profile"] = schema

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
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        print(f"[supabase_upsert] HTTP {e.code} for table={schema}.{table_name}: {body}", flush=True)
    except URLError as e:
        print(f"[supabase_upsert] URL error for table={schema}.{table_name}: {e}", flush=True)
    except Exception as e:
        print(f"[supabase_upsert] unexpected error for table={schema}.{table_name}: {e}", flush=True)

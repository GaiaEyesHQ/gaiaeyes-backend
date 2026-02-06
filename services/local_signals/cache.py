def latest_and_ref(zip_code: str, ref_hours: int = 24, window_hours: int = 3) -> tuple[dict | None, dict | None]:
    """
    Return a tuple (latest_row, reference_row) where:
      - latest_row is the newest non-expired snapshot
      - reference_row is as close as possible to ~ref_hours before latest.asof
        with progressive fallbacks so deltas still populate even when the poller
        didn't capture an exact 24h sample.
    Each element is {"asof": datetime, "payload": dict} or None.
    """
    latest = latest_row(zip_code)
    if not latest:
        return None, None

    # First try: target = latest - ref_hours within a tight window.
    target = latest["asof"] - timedelta(hours=ref_hours)
    ref = nearest_row_to(zip_code, target, window_hours=window_hours)
    if ref:
        return latest, ref

    # Second try: allow a wider window (±12h around 24h), e.g., 12..36h back.
    ref = get_previous_approx(zip_code, latest["asof"], min_hours=max(1, ref_hours - 12), max_hours=ref_hours + 12)
    if ref:
        return latest, ref

    # Final fallback: pick the second-newest snapshot for the ZIP (ignores expiration).
    z = _norm_zip(zip_code)
    row = pg.fetchrow(
        """
        select asof, payload
          from ext.local_signals_cache
         where zip = %s
         order by asof desc
         offset 1
         limit 1
        """,
        z,
    )
    if not row:
        return latest, None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return latest, {"asof": row["asof"], "payload": payload}

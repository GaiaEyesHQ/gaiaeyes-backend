@router.get("/xray/history")
async def xray_history(conn = Depends(get_db), hours: int = 24):
    """
    Time-series for GOES X-ray flux over the last N hours (default 24),
    derived from ext.xray_flux.

    Returns shape:
      {
        "ok": true,
        "data": {
          "series": {
            "long": [[ts1, flux1], ...],
            "short": [[ts1, flux1], ...]
          }
        }
      }

    Where "long" corresponds to the 0.1–0.8 nm channel and "short" to the
    0.05–0.4 nm channel, when available.
    """
    hours = max(1, min(hours, 72))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)

    rows: List[Dict[str, Any]] = []
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            await cur.execute(
                """
                select ts_utc, energy_band, flux
                from ext.xray_flux
                where ts_utc >= %s
                order by ts_utc asc
                """,
                (window_start,),
            )
            rows = await cur.fetchall() or []
    except Exception as exc:
        return {"ok": False, "data": None, "error": f"xray_history query failed: {exc}"}

    long_series: List[List[Any]] = []
    short_series: List[List[Any]] = []

    for row in rows:
        ts = _iso(row.get("ts_utc"))
        if not ts:
            continue
        flux = row.get("flux")
        if flux is None:
            continue
        try:
            fval = float(flux)
        except (TypeError, ValueError):
            continue

        energy = str(row.get("energy_band") or "").lower()
        if "0.1-0.8" in energy:
            long_series.append([ts, fval])
        elif "0.05-0.4" in energy:
            short_series.append([ts, fval])
        else:
            # If channel is unknown, you could route it to long or ignore; for now, ignore.
            continue

    return {
        "ok": True,
        "data": {
            "series": {
                "long": long_series,
                "short": short_series,
            }
        },
        "error": None,
    }
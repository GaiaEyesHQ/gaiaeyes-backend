async def assemble_for_zip(zip_code: str) -> Dict[str, Any]:
    """
    Assemble a compact local-health snapshot for a ZIP.

    Uses the NWS hourly snapshot helper (which also fetches pressure from latest
    station obs when available) + AirNow AQ + moon phase. We leave 24h deltas
    as None for now; the poller/caching layer will backfill those once we have
    time-series in cache.
    """
    lat, lon = zip_to_latlon(zip_code)

    # NWS snapshot (temp/humidity/PoP/pressure); values already normalized
    nws_snap = await nws.hourly_by_latlon(lat, lon)

    temp_c = nws_snap.get("temp_c")
    temp_then_c = None  # will be computed by cache/poller once 24h history exists
    rh_now = nws_snap.get("humidity_pct")
    pop_now = nws_snap.get("precip_prob_pct")
    baro_now = nws_snap.get("pressure_hpa")
    baro_then = None

    # Air quality (pick the highest AQI among any pollutants returned)
    aq_list = await airnow.current_by_zip(zip_code)
    aqi = category = pollutant = None
    if aq_list:
        best = max(aq_list, key=lambda a: (a.get("AQI") or 0))
        aqi = best.get("AQI")
        category = (best.get("Category") or {}).get("Name")
        pollutant = best.get("ParameterName")

    # Moon
    m = moon_phase(datetime.now(timezone.utc))

    return {
        "ok": True,
        "where": {"zip": zip_code, "lat": lat, "lon": lon},
        "weather": {
            "temp_c": temp_c,
            "temp_delta_24h_c": _delta(temp_c, temp_then_c),
            "humidity_pct": rh_now,
            "precip_prob_pct": pop_now,
            "pressure_hpa": baro_now,
            "baro_delta_24h_hpa": _delta(baro_now, baro_then),
        },
        "air": {"aqi": aqi, "category": category, "pollutant": pollutant},
        "moon": m,
        "asof": datetime.now(timezone.utc).isoformat(),
    }

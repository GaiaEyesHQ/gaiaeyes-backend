#!/usr/bin/env python3
"""
Run a small production smoke check for Gaia Eyes after launch.

The script intentionally uses only the Python standard library so it can run
from GitHub Actions, Render shells, or a local terminal without installing
project dependencies.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


def _first_env(names: Iterable[str]) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _first_token_env(names: Iterable[str]) -> str:
    value = _first_env(names)
    if not value:
        return ""
    return value.replace("\n", ",").split(",", 1)[0].strip()


BASE_URL = (os.getenv("GAIA_MONITOR_BASE_URL") or "https://gaiaeyes-backend.onrender.com").rstrip("/")
ZIP_CODE = os.getenv("GAIA_MONITOR_ZIP") or "78754"
TIMEZONE = os.getenv("GAIA_MONITOR_TZ") or "America/Chicago"
AUTH_BEARER = _first_token_env(("GAIA_MONITOR_AUTH_BEARER", "DEV_BEARER", "WRITE_TOKENS"))
DEV_USER_ID = _first_env(
    (
        "GAIA_MONITOR_DEV_USER_ID",
        "GAIA_MONITOR_USER_ID",
        "DEV_USER_ID",
        "TEST_USER_ID",
        "TEST_USER_UUID",
        "APP_REVIEW_USER_ID",
    )
)
ADMIN_BEARER = _first_token_env(
    (
        "GAIA_MONITOR_ADMIN_BEARER",
        "GAIAEYES_API_ADMIN_BEARER",
        "GAIAEYES_ADMIN_BEARER",
        "ADMIN_TOKEN",
        "DEV_BEARER",
    )
)
REQUEST_TIMEOUT = float(os.getenv("GAIA_MONITOR_TIMEOUT_SECONDS") or "20")
LAST_PROBE_WARN_MS = int(os.getenv("GAIA_MONITOR_LAST_PROBE_WARN_MS") or "60000")
ANALYTICS_MIN_EVENTS_24H = int(os.getenv("GAIA_MONITOR_ANALYTICS_MIN_EVENTS_24H") or "1")


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _headers(*, bearer: str = "") -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "gaiaeyes-post-launch-monitor/1.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if bearer and DEV_USER_ID:
        headers["X-Dev-UserId"] = DEV_USER_ID
    return headers


def _url(path: str, params: Mapping[str, Any] | None = None) -> str:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    if params:
        clean_params = {key: value for key, value in params.items() if value is not None}
        url += "?" + urllib.parse.urlencode(clean_params)
    return url


def _get_json(path: str, *, params: Mapping[str, Any] | None = None, bearer: str = "") -> dict[str, Any]:
    request = urllib.request.Request(_url(path, params), headers=_headers(bearer=bearer))
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:240]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _result(name: str, status: str, detail: str) -> CheckResult:
    return CheckResult(name=name, status=status, detail=detail)


def _status_icon(status: str) -> str:
    return {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}.get(status, status.upper())


def _iso_age_ms(value: Any) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - parsed).total_seconds() * 1000)


def check_backend_health() -> CheckResult:
    try:
        payload = _get_json("/health")
    except Exception as exc:
        return _result("backend_health", "fail", f"/health request failed: {exc}")

    if not payload.get("ok"):
        return _result("backend_health", "fail", f"/health returned ok={payload.get('ok')}")
    if payload.get("db") is False:
        return _result("backend_health", "fail", "database monitor reports db=false")

    monitor = payload.get("monitor") if isinstance(payload.get("monitor"), dict) else {}
    sticky_age = int(monitor.get("sticky_age_ms") or payload.get("db_sticky_age") or 0)
    pool = monitor.get("pool") if isinstance(monitor.get("pool"), dict) else {}
    waiting = int(pool.get("waiting") or 0)
    consec_fail = int(monitor.get("consec_fail") or 0)
    last_probe_age_ms = _iso_age_ms(monitor.get("last_probe"))
    if waiting > 0:
        return _result("backend_health", "warn", f"DB pool has waiting={waiting}")
    if consec_fail > 0:
        return _result("backend_health", "warn", f"DB monitor has consec_fail={consec_fail}")
    if last_probe_age_ms is None:
        return _result("backend_health", "warn", "DB monitor has no last_probe timestamp")
    if last_probe_age_ms > LAST_PROBE_WARN_MS:
        return _result("backend_health", "warn", f"DB monitor last_probe_age_ms={last_probe_age_ms}")
    return _result("backend_health", "pass", f"db=true healthy_state_age_ms={sticky_age} last_probe_age_ms={last_probe_age_ms}")


def _has_pollen(row: Mapping[str, Any]) -> bool:
    if str(row.get("pollen_overall_level") or "").strip():
        return True
    if row.get("pollen_overall_index") is not None:
        return True
    for key in ("tree", "grass", "weed", "mold"):
        if str(row.get(f"pollen_{key}_level") or "").strip():
            return True
        if row.get(f"pollen_{key}_index") is not None:
            return True
    return False


def check_local_forecast() -> CheckResult:
    try:
        payload = _get_json("/v1/local/check", params={"zip": ZIP_CODE})
    except Exception as exc:
        return _result("local_forecast", "fail", f"local check failed for zip={ZIP_CODE}: {exc}")

    forecast = payload.get("forecast_daily") if isinstance(payload.get("forecast_daily"), list) else []
    allergens = payload.get("allergens") if isinstance(payload.get("allergens"), dict) else {}
    pollen_days = sum(1 for row in forecast if isinstance(row, dict) and _has_pollen(row))
    if not forecast:
        return _result("local_forecast", "warn", f"zip={ZIP_CODE} returned no forecast_daily rows")
    if allergens and not pollen_days:
        return _result("local_forecast", "warn", f"current allergens present but forecast pollen rows missing for zip={ZIP_CODE}")
    return _result("local_forecast", "pass", f"zip={ZIP_CODE} forecast_days={len(forecast)} pollen_days={pollen_days}")


def check_features_today() -> CheckResult:
    if not AUTH_BEARER:
        return _result("features_today", "skip", "set GAIA_MONITOR_AUTH_BEARER for user-scoped features check")
    try:
        payload = _get_json("/v1/features/today", params={"diag": 1, "tz": TIMEZONE}, bearer=AUTH_BEARER)
    except Exception as exc:
        return _result("features_today", "fail", f"features request failed: {exc}")
    if payload.get("ok") is False:
        return _result("features_today", "fail", f"features returned ok=false error={payload.get('error')}")
    diag = payload.get("diagnostics") or payload.get("diag") or {}
    if isinstance(diag, dict):
        if diag.get("pool_timeout"):
            return _result("features_today", "fail", "features diagnostics reported pool_timeout=true")
        if diag.get("last_error"):
            return _result("features_today", "warn", f"features last_error={diag.get('last_error')}")
        return _result("features_today", "pass", f"source={payload.get('source') or diag.get('source') or 'unknown'}")
    return _result("features_today", "pass", "features payload returned")


def check_user_outlook() -> CheckResult:
    if not AUTH_BEARER:
        return _result("user_outlook", "skip", "set GAIA_MONITOR_AUTH_BEARER for user-scoped Outlook check")
    try:
        payload = _get_json("/v1/users/me/outlook", bearer=AUTH_BEARER)
    except Exception as exc:
        return _result("user_outlook", "fail", f"outlook request failed: {exc}")
    if payload.get("ok") is False:
        return _result("user_outlook", "fail", f"outlook returned ok=false error={payload.get('error')}")

    days = payload.get("daily_outlook") if isinstance(payload.get("daily_outlook"), list) else []
    if not days:
        return _result("user_outlook", "warn", "daily_outlook is empty")
    first_label = str((days[0] or {}).get("label") or "")
    if first_label.lower() == "today":
        return _result("user_outlook", "fail", "daily_outlook still starts with Today")

    driver_keys = {
        str(driver.get("key") or "")
        for day in days
        if isinstance(day, dict)
        for driver in (day.get("top_drivers") or [])
        if isinstance(driver, dict)
    }
    local_keys = driver_keys & {"pressure", "temp", "humidity", "aqi", "allergens"}
    if not local_keys:
        return _result("user_outlook", "warn", f"outlook_days={len(days)} but no local driver keys surfaced")
    return _result("user_outlook", "pass", f"days={len(days)} drivers={','.join(sorted(driver_keys))}")


def check_analytics() -> CheckResult:
    if not ADMIN_BEARER:
        return _result("analytics_summary", "skip", "set GAIA_MONITOR_ADMIN_BEARER for analytics summary check")
    try:
        payload = _get_json("/v1/admin/analytics/summary", params={"tz": TIMEZONE}, bearer=ADMIN_BEARER)
    except Exception as exc:
        return _result("analytics_summary", "fail", f"analytics summary failed: {exc}")
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    events = int(current.get("events") or 0)
    users = int(current.get("users") or 0)
    if events < ANALYTICS_MIN_EVENTS_24H:
        return _result("analytics_summary", "warn", f"events_24h={events} users_24h={users}")
    return _result("analytics_summary", "pass", f"events_24h={events} users_24h={users}")


def check_bug_reports() -> CheckResult:
    if not AUTH_BEARER:
        return _result("bug_reports", "skip", "set GAIA_MONITOR_AUTH_BEARER for bug report queue check")
    try:
        payload = _get_json("/v1/profile/bug-reports", params={"limit": 20}, bearer=AUTH_BEARER)
    except Exception as exc:
        return _result("bug_reports", "fail", f"bug report queue failed: {exc}")
    if payload.get("ok") is False:
        return _result("bug_reports", "fail", f"bug reports returned ok=false error={payload.get('error')}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    reports = data.get("reports") if isinstance(data.get("reports"), list) else []
    unalerted = [
        row for row in reports
        if isinstance(row, dict) and row.get("alert_sent") is False and row.get("alert_error")
    ]
    if unalerted:
        return _result("bug_reports", "warn", f"{len(unalerted)} recent bug report alert(s) failed")
    return _result("bug_reports", "pass", f"recent_reports={len(reports)}")


def run_checks() -> list[CheckResult]:
    return [
        check_backend_health(),
        check_local_forecast(),
        check_features_today(),
        check_user_outlook(),
        check_analytics(),
        check_bug_reports(),
    ]


def write_github_summary(results: list[CheckResult]) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        "# Gaia Eyes Post-Launch Monitor",
        "",
        f"- Base URL: `{BASE_URL}`",
        f"- Run at: `{datetime.utcnow().isoformat(timespec='seconds')}Z`",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for result in results:
        detail = result.detail.replace("|", "\\|")
        lines.append(f"| `{result.name}` | `{_status_icon(result.status)}` | {detail} |")
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    results = run_checks()
    for result in results:
        print(f"{_status_icon(result.status)} {result.name}: {result.detail}")
    write_github_summary(results)
    return 1 if any(result.status == "fail" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())

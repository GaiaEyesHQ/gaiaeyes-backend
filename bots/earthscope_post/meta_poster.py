#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meta Poster (Facebook/Instagram)
Posts Gaia Eyes daily content to FB/IG using the Graph API.

Commands:
  post-square      - posts the square caption card with caption+hashtags
  post-carousel    - posts a 3-image carousel to Instagram or Facebook
  post-carousel-fb - legacy Facebook multi-image feed post helper
  post-reel        - posts the latest EarthScope reel to Instagram or Facebook

Reads caption/hashtags from Supabase content.daily_posts (platform=default),
prefers metrics_json.sections.caption over plain caption, and resolves image URLs
from Supabase public storage first, then the legacy media repo CDN.
"""
import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter, Retry

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")


def _env_int(name: str, default: int) -> int:
  raw = (os.getenv(name) or "").strip()
  if not raw:
    return default
  try:
    return int(raw)
  except ValueError:
    logging.warning("Invalid int env %s=%r; using %s", name, raw, default)
    return default


def _env_float(name: str, default: float) -> float:
  raw = (os.getenv(name) or "").strip()
  if not raw:
    return default
  try:
    return float(raw)
  except ValueError:
    logging.warning("Invalid float env %s=%r; using %s", name, raw, default)
    return default


def _env_bool(name: str, default: bool) -> bool:
  raw = (os.getenv(name) or "").strip().lower()
  if not raw:
    return default
  return raw in ("1", "true", "yes", "on")


# --------- Env / Config ----------
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
SB_USER_ID = os.getenv("SUPABASE_USER_ID")
MEDIA_CDN_BASE = os.getenv(
  "MEDIA_CDN_BASE",
  "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/images",
).rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

MEDIA_BASE_OVERRIDE: Optional[str] = None

FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

META_GRAPH_VERSION = (os.getenv("META_GRAPH_VERSION") or "v24.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

META_CREATE_RETRY_ATTEMPTS = _env_int("META_CREATE_RETRY_ATTEMPTS", 4)
META_PUBLISH_RETRY_ATTEMPTS = _env_int("META_PUBLISH_RETRY_ATTEMPTS", 2)
META_POLL_TIMEOUT_SEC = _env_int("META_POLL_TIMEOUT_SEC", 300)
META_POLL_INTERVAL_SEC = _env_float("META_POLL_INTERVAL_SEC", 15.0)
META_POLL_MAX_INTERVAL_SEC = _env_float("META_POLL_MAX_INTERVAL_SEC", 60.0)
META_RETRY_INITIAL_DELAY_SEC = _env_float("META_RETRY_INITIAL_DELAY_SEC", 2.0)
META_RETRY_MAX_DELAY_SEC = _env_float("META_RETRY_MAX_DELAY_SEC", 30.0)
META_MEDIA_PREFLIGHT_TIMEOUT_SEC = _env_float("META_MEDIA_PREFLIGHT_TIMEOUT_SEC", 20.0)
IG_CAROUSEL_CHILD_PACING_SEC = _env_float("IG_CAROUSEL_CHILD_PACING_SEC", 1.5)
IG_CAROUSEL_SINGLE_IMAGE_FALLBACK = _env_bool("IG_CAROUSEL_SINGLE_IMAGE_FALLBACK", True)
IG_REEL_CREATE_CYCLES = _env_int("IG_REEL_CREATE_CYCLES", 2)
META_PUBLISH_RETRY_TRANSPORT_ERRORS = _env_bool("META_PUBLISH_RETRY_TRANSPORT_ERRORS", False)
IG_REEL_SHARE_TO_FEED = _env_bool("IG_REEL_SHARE_TO_FEED", False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

session = requests.Session()
adapter_retries = Retry(
  total=3,
  backoff_factor=0.7,
  status_forcelist=[429, 500, 502, 503, 504],
  allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
)
session.mount("https://", HTTPAdapter(max_retries=adapter_retries))
session.mount("http://", HTTPAdapter(max_retries=adapter_retries))


class MetaGraphError(RuntimeError):
  def __init__(
    self,
    message: str,
    *,
    status_code: Optional[int] = None,
    payload: Any = None,
    retryable: bool = False,
    attempts: int = 1,
  ):
    super().__init__(message)
    self.status_code = status_code
    self.payload = payload
    self.retryable = retryable
    self.attempts = attempts


@dataclass
class PollResult:
  ready: bool
  terminal_status: str
  attempts: int
  elapsed_sec: float
  final_payload: Dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> Dict[str, Any]:
    return asdict(self)


@dataclass
class PostResult:
  platform: str
  media_type: str
  success: bool = False
  status: str = "pending"
  post_id: Optional[str] = None
  container_id: Optional[str] = None
  fallback_used: Optional[str] = None
  retry_count: int = 0
  terminal_error: Optional[str] = None
  detail: Dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> Dict[str, Any]:
    return asdict(self)


def _clip(value: Any, limit: int = 260) -> Any:
  if value is None:
    return None
  text = str(value)
  if len(text) <= limit:
    return text
  return text[:limit] + "..."


def _sanitize_url(url: Optional[str]) -> Optional[str]:
  if not url:
    return url
  try:
    parsed = urlparse(str(url))
    if not parsed.scheme or not parsed.netloc:
      return _clip(url, 160)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
  except Exception:
    return _clip(url, 160)


def _sanitize_for_log(obj: Any) -> Any:
  if isinstance(obj, dict):
    out: Dict[str, Any] = {}
    for key, value in obj.items():
      low = str(key).lower()
      if "token" in low or low in ("apikey", "authorization"):
        out[key] = "***"
      elif low.endswith("_url") or low == "url":
        out[key] = _sanitize_url(str(value))
      elif low in ("caption", "message", "description", "status"):
        out[key] = _clip(value, 240)
      else:
        out[key] = _sanitize_for_log(value)
    return out
  if isinstance(obj, list):
    return [_sanitize_for_log(item) for item in obj]
  return _clip(obj, 240) if isinstance(obj, str) else obj


def _json_preview(obj: Any) -> str:
  try:
    return json.dumps(_sanitize_for_log(obj), ensure_ascii=False, sort_keys=True)
  except Exception:
    return _clip(repr(obj), 400)


def _backoff_delay(attempt: int) -> float:
  delay = min(META_RETRY_INITIAL_DELAY_SEC * (2 ** max(0, attempt - 1)), META_RETRY_MAX_DELAY_SEC)
  jitter = random.uniform(0.0, min(1.5, max(0.5, delay * 0.25)))
  return round(delay + jitter, 2)


def _parse_response_payload(resp: requests.Response) -> Any:
  try:
    return resp.json()
  except Exception:
    return {"raw_text": _clip(resp.text, 1000)}


def _graph_error_data(payload: Any) -> Dict[str, Any]:
  if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
    return payload["error"]
  return {}


def _is_retryable_graph_error(status_code: Optional[int], payload: Any) -> bool:
  if status_code in (408, 409, 425, 429, 500, 502, 503, 504):
    return True
  err = _graph_error_data(payload)
  if err.get("is_transient") is True:
    return True
  if err.get("type") == "OAuthException" and err.get("code") == 2:
    return True
  return False


def _graph_error_summary(label: str, status_code: Optional[int], payload: Any) -> str:
  err = _graph_error_data(payload)
  if err:
    return (
      f"{label} failed: HTTP {status_code} "
      f"type={err.get('type')} code={err.get('code')} "
      f"is_transient={err.get('is_transient')} message={_clip(err.get('message'), 240)}"
    )
  return f"{label} failed: HTTP {status_code} payload={_json_preview(payload)}"


def _graph_request(
  label: str,
  method: str,
  path: str,
  *,
  data: Optional[Dict[str, Any]] = None,
  params: Optional[Dict[str, Any]] = None,
  timeout: float = 30.0,
  attempts: int = 1,
  retry_transport_errors: bool = True,
) -> Dict[str, Any]:
  url = f"{GRAPH_BASE}/{path.lstrip('/')}"
  retry_count = 0
  for attempt in range(1, attempts + 1):
    payload_for_log = params if method.upper() == "GET" else data
    logging.info(
      "%s attempt %d/%d url=%s payload=%s",
      label,
      attempt,
      attempts,
      _sanitize_url(url),
      _json_preview(payload_for_log),
    )
    try:
      resp = session.request(method.upper(), url, data=data, params=params, timeout=timeout)
      payload = _parse_response_payload(resp)
    except requests.RequestException as exc:
      if attempt < attempts and retry_transport_errors:
        retry_count += 1
        sleep_for = _backoff_delay(attempt)
        logging.warning(
          "%s transport error on attempt %d/%d: %s; retrying in %.2fs",
          label,
          attempt,
          attempts,
          exc,
          sleep_for,
        )
        time.sleep(sleep_for)
        continue
      raise MetaGraphError(
        f"{label} transport error: {exc}",
        retryable=retry_transport_errors,
        attempts=attempt,
      ) from exc

    logging.info(
      "%s response status=%s payload=%s",
      label,
      resp.status_code,
      _json_preview(payload),
    )

    if resp.status_code < 400:
      if not isinstance(payload, dict):
        raise MetaGraphError(
          f"{label} returned non-JSON payload: {_clip(payload, 200)}",
          status_code=resp.status_code,
          payload=payload,
          attempts=attempt,
        )
      return {
        "payload": payload,
        "status_code": resp.status_code,
        "attempts": attempt,
        "retry_count": retry_count,
      }

    retryable = _is_retryable_graph_error(resp.status_code, payload)
    if attempt < attempts and retryable:
      retry_count += 1
      sleep_for = _backoff_delay(attempt)
      logging.warning(
        "%s transient Graph error on attempt %d/%d; retrying in %.2fs",
        label,
        attempt,
        attempts,
        sleep_for,
      )
      time.sleep(sleep_for)
      continue

    raise MetaGraphError(
      _graph_error_summary(label, resp.status_code, payload),
      status_code=resp.status_code,
      payload=payload,
      retryable=retryable,
      attempts=attempt,
    )

  raise MetaGraphError(f"{label} exhausted retries", attempts=attempts)


def _safe_content_length(value: Optional[str]) -> Optional[int]:
  try:
    return int(str(value or "").strip())
  except Exception:
    return None


def preflight_media_url(media_url: str, media_type: str) -> Dict[str, Any]:
  if not media_url or not str(media_url).strip():
    raise RuntimeError(f"Missing {media_type} URL for Meta publish")

  media_url = str(media_url).strip()
  if media_type == "reel":
    expected_types = ("video/mp4", "video/quicktime")
    max_bytes = 300 * 1024 * 1024
  else:
    expected_types = ("image/jpeg",)
    max_bytes = 8 * 1024 * 1024

  last_failure = None
  for method in ("HEAD", "GET"):
    headers = {"Range": "bytes=0-0"} if method == "GET" else None
    resp: Optional[requests.Response] = None
    try:
      resp = session.request(
        method,
        media_url,
        timeout=META_MEDIA_PREFLIGHT_TIMEOUT_SEC,
        allow_redirects=True,
        stream=True,
        headers=headers,
      )
      content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
      content_length = _safe_content_length(resp.headers.get("Content-Length"))
      logging.info(
        "Media preflight method=%s url=%s status=%s content_type=%s content_length=%s",
        method,
        _sanitize_url(media_url),
        resp.status_code,
        content_type or "(missing)",
        content_length if content_length is not None else "(missing)",
      )

      if method == "HEAD" and resp.status_code in (400, 403, 405):
        last_failure = RuntimeError(f"HEAD unsupported for {_sanitize_url(media_url)}")
        continue

      if resp.status_code not in (200, 206):
        raise RuntimeError(f"Media preflight failed: HTTP {resp.status_code} for {_sanitize_url(media_url)}")

      if content_type and not any(content_type.startswith(prefix) for prefix in expected_types):
        raise RuntimeError(
          f"Unexpected content-type for {media_type}: {content_type} at {_sanitize_url(media_url)}"
        )

      if content_length is not None and content_length > max_bytes:
        raise RuntimeError(
          f"{media_type} exceeds Meta size guidance: {content_length} bytes at {_sanitize_url(media_url)}"
        )

      return {
        "url": _sanitize_url(media_url),
        "method": method,
        "status_code": resp.status_code,
        "content_type": content_type,
        "content_length": content_length,
      }
    except requests.RequestException as exc:
      last_failure = RuntimeError(f"Media preflight request failed for {_sanitize_url(media_url)}: {exc}")
      if method == "HEAD":
        continue
      raise last_failure
    finally:
      if resp is not None:
        resp.close()

  raise last_failure or RuntimeError(f"Media preflight failed for {_sanitize_url(media_url)}")


# --------- Media base resolver ----------
def _resolve_media_base() -> str:
  """
  Resolve a fully-qualified base URL for rendered social images.

  Priority:
    1) MEDIA_CDN_BASE if it is a non-empty absolute URL
    2) Derive from SUPABASE_URL bucket path we use for uploads:
       {SUPABASE_URL}/storage/v1/object/public/space-visuals/social/earthscope/latest
    3) Fallback to jsDelivr media repo (legacy)
  """
  base = (MEDIA_BASE_OVERRIDE or MEDIA_CDN_BASE or "").strip().rstrip("/")
  if base and base.lower().startswith("http"):
    return base
  sb = (SUPABASE_URL or "").strip().rstrip("/")
  if sb:
    return f"{sb}/storage/v1/object/public/space-visuals/social/earthscope/latest"
  return "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/images"


def default_reel_url() -> str:
  if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is required to derive the default reel URL")
  return f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/space-visuals/social/earthscope/reels/latest/latest.mp4"


# --------- Supabase helpers ----------
def _sb_headers(schema: str = "content") -> Dict[str, str]:
  if not SB_KEY:
    raise RuntimeError("Missing Supabase key in env")
  headers = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Accept": "application/json",
  }
  if schema and schema != "public":
    headers["Accept-Profile"] = schema
  return headers


def sb_select_daily_post(day: dt.date, platform: str = "default") -> Optional[dict]:
  if not SUPABASE_REST_URL:
    return None
  url = f"{SUPABASE_REST_URL}/daily_posts"
  params = {
    "day": f"eq.{day.isoformat()}",
    "platform": f"eq.{platform}",
    "select": "day,platform,caption,hashtags,body_markdown,metrics_json",
  }
  r = session.get(url, headers=_sb_headers("content"), params=params, timeout=20)
  if r.status_code != 200:
    logging.error("Supabase posts fetch failed: %s %s", r.status_code, r.text[:200])
    return None
  data = r.json()
  return data[0] if data else None


def sb_select_latest_post(platform: str = "default") -> Optional[dict]:
  if not SUPABASE_REST_URL:
    return None
  url = f"{SUPABASE_REST_URL}/daily_posts"
  params = {
    "platform": f"eq.{platform}",
    "select": "day,platform,caption,hashtags,body_markdown,metrics_json",
    "order": "day.desc",
    "limit": "1",
  }
  r = session.get(url, headers=_sb_headers("content"), params=params, timeout=20)
  if r.status_code != 200:
    logging.error("Supabase latest posts fetch failed: %s %s", r.status_code, r.text[:200])
    return None
  data = r.json()
  return data[0] if data else None


def _select_post_with_fallback(day: dt.date, platform: str) -> tuple[Optional[dict], str, dt.date]:
  """
  Resolve a daily_posts row using fallbacks:
    1) exact (day, platform)
    2) same day on 'default'
    3) latest 'default' (any day)
  Returns: (post_or_none, effective_platform, effective_day)
  """
  post = sb_select_daily_post(day, platform)
  if post:
    return post, platform, day

  logging.warning("No content.daily_posts for day=%s platform=%s; trying same day on 'default'", day, platform)

  if platform != "default":
    default_post = sb_select_daily_post(day, "default")
    if default_post:
      return default_post, "default", day

  latest_default = sb_select_latest_post("default")
  if latest_default:
    effective_day = day
    try:
      if isinstance(latest_default.get("day"), str):
        effective_day = dt.date.fromisoformat(latest_default["day"])
    except Exception:
      pass
    logging.warning("Falling back to latest default daily_posts on %s", latest_default.get("day"))
    return latest_default, "default", effective_day

  return None, platform, day


# --------- Meta helpers ----------
def _require_meta(require_ig: bool = False) -> None:
  missing = []
  if not FB_PAGE_ID:
    missing.append("FB_PAGE_ID")
  if not FB_ACCESS_TOKEN:
    missing.append("FB_ACCESS_TOKEN")
  if require_ig and not IG_USER_ID:
    missing.append("IG_USER_ID")
  if missing:
    raise RuntimeError(f"Missing env for Meta posting: {', '.join(missing)}")


def _attempt_key(platform: str, media_type: str, caption: str, media_urls: List[str], day: Optional[str]) -> str:
  raw = json.dumps(
    {
      "platform": platform,
      "media_type": media_type,
      "caption": caption,
      "media_urls": media_urls,
      "day": day,
    },
    sort_keys=True,
    ensure_ascii=False,
  )
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _normalise_caption(caption: str, *, max_length: Optional[int] = None) -> str:
  text = (caption or "").strip()
  if max_length and len(text) > max_length:
    return text[:max_length].rstrip()
  return text


def _poll_ig_container(container_id: str, label: str) -> PollResult:
  deadline = time.monotonic() + META_POLL_TIMEOUT_SEC
  interval = max(1.0, META_POLL_INTERVAL_SEC)
  attempt = 0
  started = time.monotonic()
  last_payload: Dict[str, Any] = {}

  while time.monotonic() < deadline:
    attempt += 1
    resp = _graph_request(
      f"{label} status",
      "GET",
      container_id,
      params={"fields": "id,status_code,status", "access_token": FB_ACCESS_TOKEN},
      timeout=20,
      attempts=3,
    )
    payload = resp["payload"]
    last_payload = payload
    logging.info("%s poll attempt %d payload=%s", label, attempt, _json_preview(payload))
    status_code = (payload.get("status_code") or "").strip().upper()

    if status_code == "FINISHED":
      return PollResult(True, status_code, attempt, round(time.monotonic() - started, 2), payload)
    if status_code in ("ERROR", "EXPIRED"):
      return PollResult(False, status_code, attempt, round(time.monotonic() - started, 2), payload)

    sleep_for = min(interval, META_POLL_MAX_INTERVAL_SEC, max(0.0, deadline - time.monotonic()))
    if sleep_for <= 0:
      break
    time.sleep(sleep_for)
    interval = min(META_POLL_MAX_INTERVAL_SEC, max(interval * 1.35, META_POLL_INTERVAL_SEC))

  return PollResult(False, "TIMEOUT", attempt, round(time.monotonic() - started, 2), last_payload)


def fb_post_photo(image_url: str, caption: str, dry_run: bool = False) -> dict:
  _require_meta()
  preflight = preflight_media_url(image_url, "image")
  caption = _normalise_caption(caption)
  result = PostResult(
    platform="facebook",
    media_type="image",
    success=False,
    detail={"image_url": preflight["url"], "attempt_key": _attempt_key("facebook", "image", caption, [image_url], None)},
  )
  if dry_run:
    result.success = True
    result.status = "dry_run"
    return result.to_dict()

  resp = _graph_request(
    "FB photo create",
    "POST",
    f"{FB_PAGE_ID}/photos",
    data={"url": image_url, "caption": caption, "access_token": FB_ACCESS_TOKEN},
    attempts=META_CREATE_RETRY_ATTEMPTS,
  )
  payload = resp["payload"]
  result.success = True
  result.status = "success"
  result.retry_count = resp["retry_count"]
  result.post_id = payload.get("post_id") or payload.get("id")
  result.detail["response"] = _sanitize_for_log(payload)
  return result.to_dict()


def fb_post_multi_image(image_urls: List[str], caption: str, dry_run: bool = False) -> dict:
  """
  Publish a multi-image feed post to a Facebook Page.
  """
  _require_meta()
  caption = _normalise_caption(caption)
  result = PostResult(
    platform="facebook",
    media_type="carousel",
    success=False,
    detail={
      "image_urls": [_sanitize_url(url) for url in image_urls],
      "attempt_key": _attempt_key("facebook", "carousel", caption, image_urls, None),
    },
  )
  media_ids: List[str] = []
  total_retries = 0

  for index, image_url in enumerate(image_urls, start=1):
    preflight_media_url(image_url, "image")
    if dry_run:
      logging.info("[DRY] FB stage photo child=%d url=%s", index, _sanitize_url(image_url))
      media_ids.append(f"DRY_FB_MEDIA_{index}")
      continue
    resp = _graph_request(
      f"FB stage photo {index}",
      "POST",
      f"{FB_PAGE_ID}/photos",
      data={"url": image_url, "published": "false", "access_token": FB_ACCESS_TOKEN},
      attempts=META_CREATE_RETRY_ATTEMPTS,
    )
    payload = resp["payload"]
    media_id = payload.get("id")
    if not media_id:
      raise MetaGraphError(f"FB stage photo {index} returned no media id", payload=payload, attempts=resp["attempts"])
    media_ids.append(media_id)
    total_retries += resp["retry_count"]

  if dry_run:
    result.success = True
    result.status = "dry_run"
    result.detail["staged_media_ids"] = media_ids
    return result.to_dict()

  data = {"message": caption, "access_token": FB_ACCESS_TOKEN}
  for idx, media_id in enumerate(media_ids):
    data[f"attached_media[{idx}]"] = json.dumps({"media_fbid": media_id})

  resp = _graph_request(
    "FB multi-image publish",
    "POST",
    f"{FB_PAGE_ID}/feed",
    data=data,
    attempts=META_PUBLISH_RETRY_ATTEMPTS,
  )
  payload = resp["payload"]
  result.success = True
  result.status = "success"
  result.retry_count = total_retries + resp["retry_count"]
  result.post_id = payload.get("id")
  result.detail["staged_media_ids"] = media_ids
  result.detail["response"] = _sanitize_for_log(payload)
  return result.to_dict()


def fb_post_video(video_url: str, caption: str, dry_run: bool = False) -> dict:
  _require_meta()
  preflight = preflight_media_url(video_url, "reel")
  caption = _normalise_caption(caption)
  result = PostResult(
    platform="facebook",
    media_type="reel",
    success=False,
    detail={"video_url": preflight["url"], "attempt_key": _attempt_key("facebook", "reel", caption, [video_url], None)},
  )
  if dry_run:
    result.success = True
    result.status = "dry_run"
    return result.to_dict()

  resp = _graph_request(
    "FB reel publish",
    "POST",
    f"{FB_PAGE_ID}/videos",
    data={"file_url": video_url, "description": caption, "access_token": FB_ACCESS_TOKEN},
    attempts=META_CREATE_RETRY_ATTEMPTS,
  )
  payload = resp["payload"]
  result.success = True
  result.status = "success"
  result.retry_count = resp["retry_count"]
  result.post_id = payload.get("id")
  result.detail["response"] = _sanitize_for_log(payload)
  return result.to_dict()


def ig_post_single_image(image_url: str, caption: str, dry_run: bool = False) -> dict:
  _require_meta(require_ig=True)
  preflight = preflight_media_url(image_url, "image")
  caption = _normalise_caption(caption, max_length=2200)
  result = PostResult(
    platform="instagram",
    media_type="image",
    success=False,
    detail={"image_url": preflight["url"], "attempt_key": _attempt_key("instagram", "image", caption, [image_url], None)},
  )
  if dry_run:
    result.success = True
    result.status = "dry_run"
    return result.to_dict()

  create_resp = _graph_request(
    "IG image create",
    "POST",
    f"{IG_USER_ID}/media",
    data={"image_url": image_url, "caption": caption, "access_token": FB_ACCESS_TOKEN},
    attempts=META_CREATE_RETRY_ATTEMPTS,
  )
  creation_id = (create_resp["payload"] or {}).get("id")
  if not creation_id:
    raise MetaGraphError("IG image create returned no container id", payload=create_resp["payload"], attempts=create_resp["attempts"])
  result.container_id = creation_id
  result.retry_count += create_resp["retry_count"]

  poll = _poll_ig_container(creation_id, "IG image")
  result.detail["poll"] = poll.to_dict()
  if not poll.ready:
    result.status = "failed"
    result.terminal_error = f"IG image container {creation_id} ended in {poll.terminal_status}"
    return result.to_dict()

  publish_resp = _graph_request(
    "IG image publish",
    "POST",
    f"{IG_USER_ID}/media_publish",
    data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN},
    attempts=META_PUBLISH_RETRY_ATTEMPTS,
    retry_transport_errors=META_PUBLISH_RETRY_TRANSPORT_ERRORS,
  )
  payload = publish_resp["payload"]
  result.success = True
  result.status = "success"
  result.retry_count += publish_resp["retry_count"]
  result.post_id = payload.get("id")
  result.detail["response"] = _sanitize_for_log(payload)
  return result.to_dict()


def ig_post_carousel(image_urls: List[str], caption: str, dry_run: bool = False) -> dict:
  _require_meta(require_ig=True)
  caption = _normalise_caption(caption, max_length=2200)
  result = PostResult(
    platform="instagram",
    media_type="carousel",
    success=False,
    detail={
      "image_urls": [_sanitize_url(url) for url in image_urls],
      "attempt_key": _attempt_key("instagram", "carousel", caption, image_urls, None),
    },
  )
  children: List[str] = []

  try:
    for index, image_url in enumerate(image_urls, start=1):
      preflight_media_url(image_url, "image")
      if index > 1 and not dry_run and IG_CAROUSEL_CHILD_PACING_SEC > 0:
        logging.info("Sleeping %.2fs before IG child %d to avoid request bursts", IG_CAROUSEL_CHILD_PACING_SEC, index)
        time.sleep(IG_CAROUSEL_CHILD_PACING_SEC)
      if dry_run:
        logging.info("[DRY] IG carousel child=%d url=%s", index, _sanitize_url(image_url))
        children.append(f"DRY_CHILD_{index}")
        continue

      resp = _graph_request(
        f"IG carousel child {index}",
        "POST",
        f"{IG_USER_ID}/media",
        data={"image_url": image_url, "is_carousel_item": "true", "access_token": FB_ACCESS_TOKEN},
        attempts=META_CREATE_RETRY_ATTEMPTS,
      )
      payload = resp["payload"]
      child_id = payload.get("id")
      if not child_id:
        raise MetaGraphError(
          f"IG child {index} returned no id",
          payload=payload,
          attempts=resp["attempts"],
        )
      children.append(child_id)
      result.retry_count += resp["retry_count"]
  except Exception as exc:
    result.status = "failed"
    result.terminal_error = str(exc)
    result.detail["children"] = children
    if not dry_run and IG_CAROUSEL_SINGLE_IMAGE_FALLBACK and image_urls:
      logging.warning("IG carousel child creation failed; falling back to single image post using %s", _sanitize_url(image_urls[0]))
      fallback = ig_post_single_image(image_urls[0], caption, dry_run=False)
      fallback_result = PostResult(**fallback)
      fallback_result.fallback_used = "single_image_from_carousel"
      fallback_result.detail.setdefault("carousel_error", _clip(str(exc), 260))
      return fallback_result.to_dict()
    return result.to_dict()

  result.detail["children"] = children
  if dry_run:
    result.success = True
    result.status = "dry_run"
    return result.to_dict()

  create_resp = _graph_request(
    "IG carousel create",
    "POST",
    f"{IG_USER_ID}/media",
    data={
      "media_type": "CAROUSEL",
      "children": ",".join(children),
      "caption": caption,
      "access_token": FB_ACCESS_TOKEN,
    },
    attempts=META_CREATE_RETRY_ATTEMPTS,
  )
  payload = create_resp["payload"]
  creation_id = payload.get("id")
  if not creation_id:
    raise MetaGraphError("IG carousel create returned no container id", payload=payload, attempts=create_resp["attempts"])
  result.container_id = creation_id
  result.retry_count += create_resp["retry_count"]

  poll = _poll_ig_container(creation_id, "IG carousel")
  result.detail["poll"] = poll.to_dict()
  if not poll.ready:
    result.status = "failed"
    result.terminal_error = f"IG carousel container {creation_id} ended in {poll.terminal_status}"
    return result.to_dict()

  publish_resp = _graph_request(
    "IG carousel publish",
    "POST",
    f"{IG_USER_ID}/media_publish",
    data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN},
    attempts=META_PUBLISH_RETRY_ATTEMPTS,
    retry_transport_errors=META_PUBLISH_RETRY_TRANSPORT_ERRORS,
  )
  publish_payload = publish_resp["payload"]
  result.success = True
  result.status = "success"
  result.retry_count += publish_resp["retry_count"]
  result.post_id = publish_payload.get("id")
  result.detail["response"] = _sanitize_for_log(publish_payload)
  return result.to_dict()


def ig_post_reel(
  video_url: str,
  caption: str,
  *,
  cover_url: Optional[str] = None,
  dry_run: bool = False,
) -> dict:
  _require_meta(require_ig=True)
  preflight = preflight_media_url(video_url, "reel")
  cover_preflight = None
  if cover_url:
    cover_preflight = preflight_media_url(cover_url, "image")
  caption = _normalise_caption(caption, max_length=2200)
  result = PostResult(
    platform="instagram",
    media_type="reel",
    success=False,
    detail={
      "video_url": preflight["url"],
      "cover_url": cover_preflight["url"] if cover_preflight else None,
      "attempt_key": _attempt_key("instagram", "reel", caption, [video_url, cover_url or ""], None),
    },
  )
  if dry_run:
    result.success = True
    result.status = "dry_run"
    return result.to_dict()

  last_poll: Optional[PollResult] = None
  for cycle in range(1, max(1, IG_REEL_CREATE_CYCLES) + 1):
    create_data: Dict[str, Any] = {
      "media_type": "REELS",
      "video_url": video_url,
      "caption": caption,
      "access_token": FB_ACCESS_TOKEN,
    }
    if cover_url:
      create_data["cover_url"] = cover_url
    if IG_REEL_SHARE_TO_FEED:
      create_data["share_to_feed"] = "true"

    try:
      create_resp = _graph_request(
        f"IG reel create cycle {cycle}",
        "POST",
        f"{IG_USER_ID}/media",
        data=create_data,
        attempts=META_CREATE_RETRY_ATTEMPTS,
      )
      creation_id = (create_resp["payload"] or {}).get("id")
      if not creation_id:
        raise MetaGraphError(
          f"IG reel create cycle {cycle} returned no container id",
          payload=create_resp["payload"],
          attempts=create_resp["attempts"],
        )

      result.container_id = creation_id
      result.retry_count += create_resp["retry_count"]

      poll = _poll_ig_container(creation_id, f"IG reel cycle {cycle}")
      last_poll = poll
      result.detail[f"poll_cycle_{cycle}"] = poll.to_dict()

      if not poll.ready:
        logging.warning(
          "IG reel container %s ended in %s on cycle %d/%d",
          creation_id,
          poll.terminal_status,
          cycle,
          IG_REEL_CREATE_CYCLES,
        )
        if cycle < IG_REEL_CREATE_CYCLES:
          sleep_for = _backoff_delay(cycle)
          logging.warning("Retrying IG reel by recreating the container in %.2fs", sleep_for)
          time.sleep(sleep_for)
          continue
        result.status = "failed"
        result.terminal_error = f"IG reel container {creation_id} ended in {poll.terminal_status}"
        return result.to_dict()

      publish_resp = _graph_request(
        f"IG reel publish cycle {cycle}",
        "POST",
        f"{IG_USER_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN},
        attempts=META_PUBLISH_RETRY_ATTEMPTS,
        retry_transport_errors=META_PUBLISH_RETRY_TRANSPORT_ERRORS,
      )
      payload = publish_resp["payload"]
      result.success = True
      result.status = "success"
      result.retry_count += publish_resp["retry_count"]
      result.post_id = payload.get("id")
      result.detail["response"] = _sanitize_for_log(payload)
      return result.to_dict()
    except MetaGraphError as exc:
      result.terminal_error = str(exc)
      if cycle >= IG_REEL_CREATE_CYCLES:
        result.status = "failed"
        if last_poll:
          result.detail["last_poll"] = last_poll.to_dict()
        return result.to_dict()
      sleep_for = _backoff_delay(cycle)
      logging.warning("IG reel cycle %d/%d failed: %s; recreating in %.2fs", cycle, IG_REEL_CREATE_CYCLES, exc, sleep_for)
      time.sleep(sleep_for)

  result.status = "failed"
  result.terminal_error = result.terminal_error or "IG reel publish exhausted retries"
  return result.to_dict()


# --------- Helpers ----------
def today_in_tz() -> dt.date:
  tz = os.getenv("GAIA_TIMEZONE", "America/Chicago")
  try:
    return dt.datetime.now(ZoneInfo(tz)).date()
  except Exception:
    return dt.datetime.utcnow().date()


def default_image_urls() -> Dict[str, str]:
  base = _resolve_media_base()
  return {
    "square": f"{base}/daily_caption.jpg",
    "stats": f"{base}/daily_stats.jpg",
    "affects": f"{base}/daily_affects.jpg",
    "play": f"{base}/daily_playbook.jpg",
  }


def derive_caption_and_hashtags(post: dict) -> tuple[str, str]:
  """Return (caption, hashtags) preferring plain caption, with JSON/sections fallback when needed."""
  cap = post.get("caption") or ""
  tags = (post.get("hashtags") or "").strip()
  cap_stripped = cap.strip()
  prefer_sections = (not cap_stripped) or (cap_stripped.startswith("{") and '"sections"' in cap_stripped)

  try:
    metrics = post.get("metrics_json")
    if isinstance(metrics, str):
      metrics = json.loads(metrics)
    if prefer_sections and isinstance(metrics, dict):
      sections = metrics.get("sections") or {}
      if isinstance(sections, dict):
        cap2 = sections.get("caption")
        if cap2 and str(cap2).strip():
          cap = str(cap2)
  except Exception:
    pass

  def _try_parse_sections(text: str) -> Optional[str]:
    try:
      obj = json.loads(text.lstrip())
      if isinstance(obj, str) and obj.strip().startswith("{"):
        obj = json.loads(obj)
      if isinstance(obj, dict):
        sections = obj.get("sections") or {}
        if isinstance(sections, dict) and sections.get("caption"):
          return str(sections["caption"])
    except Exception:
      return None
    return None

  cap = cap.strip()
  if cap.startswith("{") and '"sections"' in cap:
    parsed = _try_parse_sections(cap)
    if parsed:
      cap = parsed

  if (not cap) or (cap.startswith("{") and '"sections"' in cap):
    body = (post.get("body_markdown") or "").strip()
    if body.startswith("{") and '"sections"' in body:
      parsed = _try_parse_sections(body)
      if parsed:
        cap = parsed

  cap = cap.strip()
  if tags:
    return cap + "\n\n" + tags, tags
  return cap, tags


def _caption_from_file(path: Optional[str]) -> Optional[str]:
  if not path:
    return None
  text = Path(path).read_text(encoding="utf-8").strip()
  return text or None


def _result_exit_code(result: Dict[str, Any]) -> int:
  if result.get("success"):
    return 0
  return 1


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("cmd", choices=["post-square", "post-carousel", "post-carousel-fb", "post-reel"], help="What to publish")
  ap.add_argument("--date", default=today_in_tz().isoformat(), help="YYYY-MM-DD (defaults to GAIA_TIMEZONE today)")
  ap.add_argument("--platform", default="default", help="Target platform: default|ig|fb")
  ap.add_argument("--dry-run", action="store_true")
  ap.add_argument(
    "--media-base",
    dest="media_base",
    default=None,
    help="Override image base URL (e.g., https://.../space-visuals/social/earthscope/latest)",
  )
  ap.add_argument("--video-url", default=None, help="Override the reel/video URL to publish")
  ap.add_argument("--cover-url", default=None, help="Optional public cover image URL for reels")
  ap.add_argument("--caption-file", default=None, help="Optional path to a caption file")
  args = ap.parse_args()

  global MEDIA_BASE_OVERRIDE
  if args.media_base:
    MEDIA_BASE_OVERRIDE = args.media_base.strip().rstrip("/")

  logging.info("Using Meta Graph API version: %s", META_GRAPH_VERSION)
  logging.info("Using media base: %s", _resolve_media_base())

  caption_override = _caption_from_file(args.caption_file)

  day = dt.date.fromisoformat(args.date)
  post, effective_platform, effective_day = _select_post_with_fallback(day, args.platform)
  if args.cmd != "post-reel" or not caption_override:
    if not post:
      logging.error("No content.daily_posts available for day=%s (platform %s or default)", day, args.platform)
      sys.exit(2)
    day = effective_day
    logging.info("Post day=%s platform=%s caption[0:80]=%s", day, effective_platform, (post.get("caption") or "")[:80])

  urls = default_image_urls()

  if args.cmd == "post-square":
    caption = caption_override or derive_caption_and_hashtags(post)[0]
    logging.info("Derived caption (len=%d): %s", len(caption), _clip(caption, 180))
    result = fb_post_photo(urls["square"], caption, dry_run=args.dry_run)
    logging.info("FB result: %s", _json_preview(result))
    if args.platform.lower() in ("ig", "instagram"):
      ig_result = ig_post_single_image(urls["square"], caption, dry_run=args.dry_run)
      logging.info("IG result: %s", _json_preview(ig_result))
      sys.exit(_result_exit_code(ig_result))
    sys.exit(_result_exit_code(result))

  if args.cmd == "post-carousel":
    caption = caption_override or derive_caption_and_hashtags(post)[0]
    logging.info("Derived caption (len=%d): %s", len(caption), _clip(caption, 180))
    image_urls = [urls["stats"], urls["affects"], urls["play"]]
    platform = (args.platform or "").lower()
    if platform in ("fb", "facebook"):
      result = fb_post_multi_image(image_urls, caption, dry_run=args.dry_run)
      logging.info("FB result: %s", _json_preview(result))
    else:
      result = ig_post_carousel(image_urls, caption, dry_run=args.dry_run)
      logging.info("IG result: %s", _json_preview(result))
    sys.exit(_result_exit_code(result))

  if args.cmd == "post-carousel-fb":
    caption = caption_override or derive_caption_and_hashtags(post)[0]
    logging.info("Derived caption (len=%d): %s", len(caption), _clip(caption, 180))
    result = fb_post_multi_image([urls["stats"], urls["affects"], urls["play"]], caption, dry_run=args.dry_run)
    logging.info("FB result: %s", _json_preview(result))
    sys.exit(_result_exit_code(result))

  if args.cmd == "post-reel":
    caption = caption_override
    if not caption:
      if not post:
        logging.error("No content.daily_posts available for reel caption resolution")
        sys.exit(2)
      caption = derive_caption_and_hashtags(post)[0]
    logging.info("Derived reel caption (len=%d): %s", len(caption), _clip(caption, 180))
    video_url = args.video_url or default_reel_url()
    cover_url = args.cover_url or urls["square"]
    platform = (args.platform or "").lower()
    if platform in ("fb", "facebook"):
      result = fb_post_video(video_url, caption, dry_run=args.dry_run)
      logging.info("FB result: %s", _json_preview(result))
      sys.exit(_result_exit_code(result))
    result = ig_post_reel(video_url, caption, cover_url=cover_url, dry_run=args.dry_run)
    logging.info("IG result: %s", _json_preview(result))
    sys.exit(_result_exit_code(result))


if __name__ == "__main__":
  try:
    main()
  except Exception:
    logging.exception("Post failed")
    sys.exit(1)

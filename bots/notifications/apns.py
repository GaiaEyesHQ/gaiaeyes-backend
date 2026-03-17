from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _parse_der_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    count = first & 0x7F
    value = int.from_bytes(data[offset : offset + count], "big")
    return value, offset + count


def _der_to_raw_ecdsa_sig(der: bytes, size: int = 32) -> bytes:
    if not der or der[0] != 0x30:
        raise RuntimeError("unexpected ECDSA DER signature")
    seq_len, idx = _parse_der_length(der, 1)
    seq_end = idx + seq_len
    if der[idx] != 0x02:
        raise RuntimeError("missing r integer in ECDSA signature")
    r_len, idx = _parse_der_length(der, idx + 1)
    r = der[idx : idx + r_len]
    idx += r_len
    if der[idx] != 0x02:
        raise RuntimeError("missing s integer in ECDSA signature")
    s_len, idx = _parse_der_length(der, idx + 1)
    s = der[idx : idx + s_len]
    idx += s_len
    if idx != seq_end:
        raise RuntimeError("unexpected trailing ECDSA signature data")
    r = r.lstrip(b"\x00").rjust(size, b"\x00")
    s = s.lstrip(b"\x00").rjust(size, b"\x00")
    return r + s


def _normalized_private_key_pem(private_key: str) -> str:
    return private_key.replace("\\n", "\n").strip() + "\n"


def create_provider_token(
    *,
    team_id: str,
    key_id: str,
    private_key_pem: str,
    issued_at: datetime | None = None,
) -> str:
    now = (issued_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    header = _b64url(json.dumps({"alg": "ES256", "kid": key_id}, separators=(",", ":")).encode("utf-8"))
    claims = _b64url(json.dumps({"iss": team_id, "iat": int(now.timestamp())}, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{claims}".encode("ascii")

    key_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".p8", delete=False) as handle:
            handle.write(_normalized_private_key_pem(private_key_pem))
            key_path = handle.name
        proc = subprocess.run(
            ["openssl", "dgst", "-binary", "-sha256", "-sign", key_path],
            input=signing_input,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"openssl signing failed: {stderr or 'unknown error'}")
        signature = _der_to_raw_ecdsa_sig(proc.stdout)
        return f"{header}.{claims}.{_b64url(signature)}"
    finally:
        if key_path:
            try:
                os.unlink(key_path)
            except OSError:
                pass


def send_apns_notification(
    *,
    device_token: str,
    body: Dict[str, Any],
    auth_token: str,
    topic: str,
    sandbox: bool = False,
    collapse_id: str | None = None,
) -> Dict[str, Any]:
    host = "api.sandbox.push.apple.com" if sandbox else "api.push.apple.com"
    url = f"https://{host}/3/device/{device_token}"
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--http2",
        "--output",
        "-",
        "--write-out",
        "\n%{http_code}",
        "--header",
        f"authorization: bearer {auth_token}",
        "--header",
        f"apns-topic: {topic}",
        "--header",
        "apns-push-type: alert",
        "--header",
        "apns-priority: 10",
        "--header",
        "content-type: application/json",
        "--data-binary",
        "@-",
        url,
    ]
    if collapse_id:
        cmd.extend(["--header", f"apns-collapse-id: {collapse_id[:64]}"])

    proc = subprocess.run(cmd, input=payload, capture_output=True, check=False)
    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    body_text, _, status_text = stdout.rpartition("\n")
    try:
        status_code = int(status_text.strip())
    except Exception:
        status_code = 0

    parsed: Dict[str, Any] = {}
    if body_text.strip():
        try:
            parsed = json.loads(body_text)
        except Exception:
            parsed = {"raw": body_text.strip()}

    return {
        "ok": proc.returncode == 0 and status_code == 200,
        "status_code": status_code,
        "body": parsed,
        "raw_body": body_text.strip(),
        "stderr": stderr,
    }

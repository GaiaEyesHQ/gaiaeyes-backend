from scripts.ingest_space_visuals import (
    ingest_aia_304,
    ingest_hmi_intensity,
    ingest_drap_now,
    ingest_lasco_c2,
    alias_aurora_viewline,
    upload_rendered_png,
    upload_alias,
    upload_bytes,
    upsert_visual_row,
)


def main():
    captured_at = datetime.datetime.now(tz=datetime.timezone.utc)
    ingest_aia_304(captured_at)
    ingest_hmi_intensity(captured_at)
    ingest_drap_now(captured_at)
    ingest_lasco_c2(captured_at)
    # other ingest calls...

def ingest_aia_304(captured_at):
    # ... existing code ...
    rel = f"nasa/aia_304/aia_304_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, img_bytes, content_type=content_type)
    # Alias for "latest" solar disc; keep .jpg name for compatibility with existing image_path rows
    latest_alias = "nasa/aia_304/latest.jpg"
    upload_alias(latest_alias, public, content_type=content_type)
    upsert_visual_row("aia_304", latest_alias, "SDO/AIA (via Helioviewer)", "aia_304", captured_at)

def ingest_hmi_intensity(captured_at):
    # ... existing code ...
    rel = f"nasa/hmi_intensity/hmi_intensity_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, img_bytes, content_type=content_type)
    # Alias for "latest" HMI intensity; keep .jpg name for compatibility with existing image_path rows
    latest_alias = "nasa/hmi_intensity/latest.jpg"
    upload_alias(latest_alias, public, content_type=content_type)
    upsert_visual_row("hmi_intensity", latest_alias, "SDO/HMI (via Helioviewer)", "hmi_intensity", captured_at)

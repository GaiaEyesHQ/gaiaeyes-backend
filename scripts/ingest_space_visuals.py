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

from scripts.ingest_space_visuals import ingest_aia_304, ingest_hmi_intensity
import datetime

def ingest_aia_304():
    captured_at = datetime.datetime.now(tz=datetime.timezone.utc)
    ingest_aia_304(captured_at)

def ingest_hmi_intensity():
    captured_at = datetime.datetime.now(tz=datetime.timezone.utc)
    ingest_hmi_intensity(captured_at)

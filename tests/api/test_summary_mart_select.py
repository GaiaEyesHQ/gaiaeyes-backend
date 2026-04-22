from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers import summary


def test_summary_mart_select_uses_daily_summary_cycle_updated_at():
    assert "ds.cycle_updated_at as cycle_updated_at" in summary._MART_SELECT
    assert "df.cycle_updated_at" not in summary._MART_SELECT

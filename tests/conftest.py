import os
import tempfile
from pathlib import Path

# calendar_sync.config reads config.yaml at import time (and blows up if it is
# missing), so point the whole test session at a throwaway one before any
# calendar_sync module gets imported.
_tmp = Path(tempfile.mkdtemp(prefix="calendar-sync-tests-"))
_cfg = _tmp / "config.yaml"
_cfg.write_text("calendars: []\nsync_window_days: 14\n")
os.environ.setdefault("CONFIG_PATH", str(_cfg))
os.environ.setdefault("DB_PATH", str(_tmp / "calendar_sync.db"))

# Keep the run hermetic: no local .env, no telemetry exporter reaching out.
os.environ["ENV_PATH"] = str(_tmp / "absent.env")
os.environ["UPTRACE_DSN"] = ""
os.environ["OLTP_EXPORTER_ENDPOINT"] = ""

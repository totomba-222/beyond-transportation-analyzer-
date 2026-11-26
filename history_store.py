"""Persistent weekly-history storage for the Streamlit app.

The path can be overridden with BT_HISTORY_PATH. The default is a data folder
next to the application, so the history survives normal Streamlit reruns and
restarts on a persistent deployment.
"""
import os
from pathlib import Path

import history as HI


_DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "weekly_history.csv"


def path():
    return Path(os.environ.get("BT_HISTORY_PATH", str(_DEFAULT_PATH)))


def load():
    p = path()
    if not p.exists():
        return None
    try:
        return HI.from_csv(str(p))
    except Exception:
        return None


def save(frame):
    if frame is None:
        return False
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(HI.to_csv(frame), encoding="utf-8")
    tmp.replace(p)
    return True

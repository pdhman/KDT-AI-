from __future__ import annotations
import json
import pandas as pd
from pathlib import Path

def save_json(obj: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def save_series(s: pd.Series, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(path, header=True, encoding="utf-8-sig")

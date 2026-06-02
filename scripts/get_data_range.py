from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / "data" / "amv_daily.csv"
    frame = pd.read_csv(path)
    dates = pd.to_datetime(frame["date"]).dt.date
    print(json.dumps({"start": dates.min().isoformat(), "end": dates.max().isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


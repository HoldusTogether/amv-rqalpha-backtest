# 0AMV RQAlpha Backtest

Personal research project for testing a 0AMV `+4% / -2.3%` ETF timing strategy in RQAlpha.

## Layout

- `strategy/amv_rules.py`: 0AMV threshold state machine and ETF selection logic.
- `strategy/amv_band_strategy.py`: RQAlpha strategy entrypoint and order logic.
- `data/amv_daily.csv`: 0AMV daily bars or generated 0AMV proxy.
- `data/concept_flow.csv`: daily concept fund-flow snapshots.
- `data/concept_etf_map.csv`: concept to ETF mapping.
- `scripts/validate_data.py`: validates required CSV fields.
- `scripts/preview_signals.py`: previews strategy signals without RQAlpha.
- `scripts/run_backtest.ps1`: runs the RQAlpha backtest and exports dashboard data.
- `scripts/update_data.ps1`: fetches free data through AKShare.
- `web/`: local dashboard.
- `docs/DATA_SOURCES.md`: free data source notes and limitations.

## Rules

- 0AMV bullish daily bar with `pct_change >= +4%`: confirm long band, buy the ETF mapped from the strongest concept fund inflow, target weight `100%`.
- While in the long band, hold unless 0AMV breaks below the low of the anchor `+4%` bar.
- 0AMV `pct_change <= -1.5%`: reduce the active ETF to `50%`.
- 0AMV `pct_change <= -2.3%`: clear the active ETF.
- If the long band anchor low is broken: clear the active ETF.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\rqalpha.exe download-bundle -d .\bundle --confirm
```

RQAlpha usually downloads data to `.\bundle\bundle`; `scripts/run_backtest.ps1` is configured for that path.

## Data Automation

Fetch free data with AKShare:

```powershell
.\scripts\update_data.ps1
```

This updates:

- `data/amv_daily.csv` using an automatic 0AMV proxy.
- `data/concept_flow.csv` by appending the latest concept fund-flow snapshot.
- `data/etf_spot.csv` and high-confidence additions to `data/concept_etf_map.csv`.

Important limitation: the generated 0AMV proxy is not Compass original 0AMV. Free concept fund-flow APIs are best used as daily snapshots; historical backfill is unstable.

## Run

Validate data:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_data.py
```

Preview signals:

```powershell
.\.venv\Scripts\python.exe .\scripts\preview_signals.py
```

Run backtest:

```powershell
.\scripts\run_backtest.ps1
```

`run_backtest.ps1` reads the start/end dates from `data/amv_daily.csv` automatically. You can override the range:

```powershell
.\scripts\run_backtest.ps1 2024-01-02 2024-01-08
```

## Dashboard

Start the local dashboard:

```powershell
.\scripts\serve_dashboard.ps1
```

Open:

```text
http://127.0.0.1:8765
```


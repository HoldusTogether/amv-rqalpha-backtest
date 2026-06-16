# 0AMV RQAlpha Backtest

Personal research project for testing a 0AMV `+3.5% / -2% / -3%` ETF timing strategy in RQAlpha.

## Layout

- `strategy/amv_rules.py`: 0AMV threshold state machine and ETF selection logic.
- `strategy/amv_band_strategy.py`: RQAlpha strategy entrypoint and order logic.
- `data/amv_daily.csv`: 0AMV daily bars (from Compass software).
- `data/concept_daily_returns.csv`: concept index daily returns.
- `data/etf_flow.csv`: ETF daily bars with OHLC + net_flow.
- `data/concept_etf_map.csv`: concept to ETF mapping.
- `scripts/validate_data.py`: validates required CSV fields.
- `scripts/preview_signals.py`: previews strategy signals without RQAlpha.
- `scripts/run_backtest.ps1`: runs the RQAlpha backtest and exports dashboard data.
- `scripts/update_data.ps1`: fetches data from local TDX/Compass or AKShare fallback.
- `web/`: local dashboard.
- `docs/DATA_SOURCES.md`: data source notes and limitations.

## Rules

- 0AMV bullish daily bar with `pct_change >= +3.5%`: confirm long band, buy the ETF mapped from the strongest concept momentum, target weight `100%`.
- While in the long band, hold unless 0AMV breaks below the low of the anchor `+3.5%` bar.
- 0AMV `pct_change <= -2%`: reduce position to `50%` of current (i.e., half the current position).
- 0AMV `pct_change <= -3%`: clear all positions.
- If the long band anchor low is broken: clear all positions.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\rqalpha.exe download-bundle -d .\bundle --confirm
```

RQAlpha usually downloads data to `.\bundle\bundle`; `scripts/run_backtest.ps1` is configured for that path.

## Data Sources

Primary data is extracted from local installations:
- **0AMV**: Compass software `day.vdat` file (Z_SK0AMV)
- **Concept/ETF**: TDX software `.day` files

AKShare is used as fallback when local data is unavailable.

```powershell
.\scripts\update_data.ps1
```

This updates:
- `data/amv_daily.csv` from Compass
- `data/concept_daily_returns.csv` from TDX
- `data/etf_flow.csv` from TDX
- RQAlpha bundle with latest ETF data

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

```
http://127.0.0.1:8765
```

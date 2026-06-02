$StartDate = ""
$EndDate = ""

if ($args.Count -ge 1) {
  $StartDate = $args[0]
}
if ($args.Count -ge 2) {
  $EndDate = $args[1]
}

$Root = Split-Path -Parent $PSScriptRoot
$Rqalpha = Join-Path $Root ".venv\Scripts\rqalpha.exe"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Bundle = Join-Path $Root "bundle\bundle"
$Strategy = Join-Path $Root "strategy\amv_band_strategy.py"
$Report = Join-Path $Root "reports\report"
$Output = Join-Path $Root "reports\result.pkl"

$env:PYTHONPATH = "$(Join-Path $Root "strategy");$env:PYTHONPATH"

$Range = (& $Python (Join-Path $Root "scripts\get_data_range.py")) | ConvertFrom-Json
if (-not $StartDate) {
  $StartDate = $Range.start
}
if (-not $EndDate) {
  $EndDate = $Range.end
}

& $Rqalpha run `
  -d $Bundle `
  -f $Strategy `
  -s $StartDate `
  -e $EndDate `
  -a stock 1000000 `
  -fq 1d `
  --matching-type current_bar `
  --report $Report `
  -o $Output `
  --progress

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

& $Python (Join-Path $Root "scripts\export_dashboard_data.py")

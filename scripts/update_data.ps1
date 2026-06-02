$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "=== Step 1: Export 0AMV from 指南针 local data ==="
$ExtractScript = Join-Path $Root "scripts\extract_amv_klines.py"
if (Test-Path $ExtractScript) {
    & $Python $ExtractScript
} else {
    Write-Warning "extract_amv_klines.py not found; skip"
}

Write-Host "`n=== Step 2 (primary): Fetch concept daily returns from AKShare ==="
$AkshareScript = Join-Path $Root "scripts\fetch_concept_data_akshare.py"
if (Test-Path $AkshareScript) {
    & $Python $AkshareScript
} else {
    Write-Warning "fetch_concept_data_akshare.py not found; skip"
}

Write-Host "`n=== Step 2 (fallback): Build concept returns from TDX .day files ==="
$TdxScript = Join-Path $Root "scripts\build_concept_returns.py"
if (Test-Path $TdxScript) {
    & $Python $TdxScript
} else {
    Write-Warning "build_concept_returns.py not found; skip"
}

Write-Host "`n=== Step 3: Build ETF flow data from TDX .day files ==="
$EtfFlowScript = Join-Path $Root "scripts\build_etf_flow_from_tdx.py"
if (Test-Path $EtfFlowScript) {
    & $Python $EtfFlowScript
} else {
    Write-Warning "build_etf_flow_from_tdx.py not found; skip"
}

Write-Host "`n=== Step 4: Update RQAlpha bundle ETFs (funds.h5 + indexes.h5) with new data ==="
$BundleScript = Join-Path $Root "scripts\update_bundle_etfs_from_tdx.py"
if (Test-Path $BundleScript) {
    & $Python $BundleScript
} else {
    Write-Warning "update_bundle_etfs_from_tdx.py not found; skip"
}

Write-Host "`n=== Update complete ==="

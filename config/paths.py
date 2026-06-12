"""Externalized data paths - supports environment variable overrides."""
from __future__ import annotations

import os
from pathlib import Path


class DataPaths:
    """Data source paths with environment variable override support."""

    # Compass 0AMV data
    COMPASS_VDAT: str = os.getenv(
        "COMPASS_VDAT",
        r"D:\Program Files (x86)\zhinanzhen\ANALYSE\Data\ChinaStk\Z_SK\day.vdat"
    )

    # TDX data directories
    TDX_DIR: str = os.getenv("TDX_DIR", r"D:\new_tdx")
    TDX_SH_DIR: str = os.path.join(TDX_DIR, r"vipdoc\sh\lday")
    TDX_SZ_DIR: str = os.path.join(TDX_DIR, r"vipdoc\sz\lday")
    TDX_INFOHARBOR: str = os.path.join(TDX_DIR, r"T0002\hq_cache\infoharbor_block.dat")

    # Block files
    TDX_BLOCKNEW: str = os.path.join(TDX_DIR, r"T0002\blocknew")


paths = DataPaths()

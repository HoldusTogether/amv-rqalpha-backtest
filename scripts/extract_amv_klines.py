"""Extract full 0AMV K-line data from day.vdat and combine with latest data."""

import struct
from pathlib import Path

import pandas as pd


def parse_klines(data: bytes, start_offset: int) -> list[dict]:
    """Parse 20-byte K-line records from data starting at offset."""
    kl = []
    pos = start_offset
    while pos + 20 <= len(data):
        chunk = data[pos:pos + 20]
        date_val = struct.unpack("<I", chunk[:4])[0]
        y = date_val // 10000
        m = (date_val % 10000) // 100
        d = date_val % 100
        if y < 1990 or y > 2030 or m < 1 or m > 12 or d < 1 or d > 31:
            if data[pos:pos + 4] == b"\x00\x00\x00\x00":
                break
            pos += 1
            continue
        try:
            o, h, l, c = struct.unpack("<ffff", chunk[4:20])
        except:
            break
        kl.append({
            "date": f"{y:04d}-{m:02d}-{d:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
        })
        pos += 20
    return kl


def main():
    vdat = Path(r"D:\Program Files (x86)\zhinanzhen\ANALYSE\Data\ChinaStk\Z_SK\day.vdat").read_bytes()

    # Find all K-line entries (after index entries 0-1 which use FA format)
    entries = []
    pos = 0
    while True:
        zsk = vdat.find(b"Z_SK0AMV", pos)
        if zsk < 0:
            break
        entries.append(zsk)
        pos = zsk + 1

    print(f"Found {len(entries)} Z_SK0AMV entries")

    # Parse K-lines from entries 2+ (skip FA-format entries 0-1)
    all_klines = []
    for ent_idx in range(2, len(entries)):
        ent_off = entries[ent_idx]
        d_off = ent_off + 16
        while d_off < len(vdat) and vdat[d_off] == 0:
            d_off += 1
        if d_off + 20 > len(vdat):
            continue

        kl = parse_klines(vdat, d_off)
        if kl:
            all_klines.extend(kl)
            print(f"  Entry {ent_idx}: {kl[0]['date']} -> {kl[-1]['date']} ({len(kl)} lines)")

    if not all_klines:
        print("No K-lines found!")
        return

    # Build DataFrame, keep latest of duplicates
    df = pd.DataFrame(all_klines)
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.sort_values("date").reset_index(drop=True)
    df["pct_change"] = df["close"].pct_change().fillna(0.0)

    print(f"\n=== Full 0AMV K-line data ===")
    print(f"Rows: {len(df)}")
    print(f"Range: {df['date'].iloc[0]} -> {df['date'].iloc[-1]}")
    cvals = df["close"]
    print(f"Close: {cvals.min():.2f} - {cvals.max():.2f}")
    print(f"Latest: date={df['date'].iloc[-1]}, close={cvals.iloc[-1]:.2f}, "
          f"pct={df['pct_change'].iloc[-1]:+.4f}")

    pct = df["pct_change"]
    print(f"\npct stats: mean={pct.mean():.6f}, std={pct.std():.6f}")
    print(f"max={pct.max():.4f}, min={pct.min():.4f}")
    longs = (pct >= 0.04).sum()
    shorts = (pct <= -0.023).sum()
    print(f"Long signals (>=+4%): {longs}")
    print(f"Short signals (<=-2.3%): {shorts}")

    print(f"\nLast 10 rows:")
    print(df.tail(10)[["date", "open", "high", "low", "close",
                        "pct_change"]].to_string(index=False))

    # Save
    out_path = Path(__file__).resolve().parents[1] / "data" / "amv_daily.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()

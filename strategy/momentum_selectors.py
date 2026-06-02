"""动量选标函数，供策略文件导入使用。
方向A: select_etf_by_momentum — ETF价格动量轮动
方向B: select_etf_by_concept_momentum — 概念行业轮动（按ETF聚合平均）

数据来源：
- etf_flow.csv（RQAlpha bundle，真实ETF OHLC）
- concept_daily_returns.csv（TDX .day 文件，真实概念价格数据）
- concept_etf_map.csv（概念ETF映射表）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_etf_daily(path: str | Path) -> pd.DataFrame:
    """从 etf_flow.csv 加载ETF日线。"""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["order_book_id", "date"])
    df["return"] = df.groupby("order_book_id")["close"].pct_change()
    return df


def select_etf_by_momentum(
    etf_daily: pd.DataFrame,
    trade_date: pd.Timestamp,
    window: int = 5,
) -> dict[str, Any]:
    """
    方向A：选择过去N日累计涨幅最大的ETF。
    window=1 时使用单日涨幅，window>1 时使用N日累计涨幅。
    数据来源：etf_flow.csv（RQAlpha bundle，真实ETF OHLC）。
    """
    trade_date = pd.Timestamp(trade_date).normalize()
    hist = etf_daily[etf_daily["date"] <= trade_date].copy()
    if hist.empty:
        return {"order_book_id": "510050.XSHG", "momentum": 0.0, "etf_name": "上证50ETF"}

    last_date = hist["date"].max()
    cutoff = last_date - pd.Timedelta(days=window * 2)
    recent = hist[hist["date"] >= cutoff].copy()

    best_etf = None
    best_mom = -float("inf")

    for oid in recent["order_book_id"].unique():
        etf_data = recent[recent["order_book_id"] == oid].sort_values("date")
        if len(etf_data) < window:
            continue
        if window == 1:
            if len(etf_data) < 2:
                continue
            mom = etf_data["close"].iloc[-1] / etf_data["close"].iloc[-2] - 1
        else:
            mom = etf_data["close"].iloc[-1] / etf_data["close"].iloc[-window] - 1
        if mom > best_mom:
            best_mom = mom
            best_etf = oid

    if best_etf is None:
        return {"order_book_id": "510050.XSHG", "momentum": 0.0, "etf_name": "上证50ETF"}

    name_row = etf_daily[etf_daily["order_book_id"] == best_etf]
    etf_name = name_row.iloc[0].get("etf_name", "") if not name_row.empty else ""
    return {"order_book_id": best_etf, "momentum": round(best_mom, 6), "etf_name": etf_name}


def load_etf_candidates(path: str | Path) -> list[str]:
    """从 etf_flow.csv 加载可交易ETF列表。"""
    df = pd.read_csv(path)
    return sorted(df["order_book_id"].dropna().unique().tolist())


def load_concept_daily(path: str | Path) -> pd.DataFrame:
    """
    加载概念日线。优先加载 path（AKShare 输出，2019+），
    若不存在或为空则回退到 concept_daily_returns_tdx.csv（TDX，2005+）。
    当两个数据源都存在时，AKShare 覆盖较新日期，TDX 补充较早日期。
    """
    path = Path(path)
    tdx_path = path.parent / "concept_daily_returns_tdx.csv"

    def _load(csv_path: Path) -> pd.DataFrame:
        df = pd.read_csv(csv_path)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values(["concept", "date"])

    has_akshare = path.exists()
    has_tdx = tdx_path.exists()

    if not has_akshare and not has_tdx:
        return pd.DataFrame(columns=["date", "concept", "close", "return"])

    # Load AKShare primary
    if has_akshare:
        akshare_df = _load(path)
        if not akshare_df.empty:
            if not has_tdx:
                return akshare_df
            # Supplement with TDX data for dates before AKShare coverage
            tdx_df = _load(tdx_path)
            akshare_min = akshare_df["date"].min()
            before = tdx_df[tdx_df["date"] < akshare_min]
            if before.empty:
                return akshare_df
            combined = pd.concat([before, akshare_df], ignore_index=True)
            return combined.sort_values(["date", "concept"]).drop_duplicates(
                subset=["date", "concept"], keep="last"
            )

    # Fallback to TDX
    if has_tdx:
        return _load(tdx_path)

    return pd.DataFrame(columns=["date", "concept", "close", "return"])


def _pick_weighted_top_n(
    ranked: list[tuple[str, float, str]],
    top_n: int = 3,
    rng: Any = None,
) -> tuple[str, str]:
    """从动量排名前N的ETF中按动量权重随机选一个。

    Args:
        ranked: [(oid, avg_momentum, best_concept), ...] 按动量降序排列
        top_n: 候选数量
        rng: random.Random 实例，用于可复现随机

    Returns:
        (selected_oid, best_concept)
    """
    if not ranked:
        return ("510050.XSHG", "")
    candidates = ranked[:min(top_n, len(ranked))]
    if len(candidates) == 1:
        return (candidates[0][0], candidates[0][2])

    weights = []
    for _, mom, _ in candidates:
        w = max(mom, 0.0)  # 只使用正动量作为权重
        if w <= 0:
            w = 0.01       # 给非正动量一个最低权重，避免概率为0
        weights.append(w)
    total = sum(weights)
    if total <= 0:
        return (candidates[0][0], candidates[0][2])

    if rng is None:
        import random as _rng
        rng = _rng
    r = rng.random() * total
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return (candidates[i][0], candidates[i][2])
    return (candidates[-1][0], candidates[-1][2])


def load_concept_etf_map(path: str | Path) -> dict[str, tuple[str, str]]:
    """
    加载概念ETF映射表。
    返回 {concept: (order_book_id, etf_name)}
    每个概念只保留最高优先级ETF。
    """
    df = pd.read_csv(path)
    df = df.sort_values("priority").drop_duplicates("concept", keep="first")
    mapping: dict[str, tuple[str, str]] = {}
    for _, row in df.iterrows():
        mapping[row["concept"]] = (row["order_book_id"], row["etf_name"])
    return mapping


def build_etf_concept_map(
    concept_map: dict[str, tuple[str, str]],
) -> dict[str, list[str]]:
    """
    反向构建 ETF -> [concept列表] 映射
    用于按ETF聚合概念动量。
    """
    etf_to_concepts: dict[str, list[str]] = {}
    for concept, (oid, _) in concept_map.items():
        if oid not in etf_to_concepts:
            etf_to_concepts[oid] = []
        etf_to_concepts[oid].append(concept)
    return etf_to_concepts


def select_etf_by_concept_momentum(
    concept_daily: pd.DataFrame,
    concept_map: dict[str, tuple[str, str]],
    trade_date: pd.Timestamp,
    window: int = 5,
    avoid_etfs: set[str] | None = None,
    top_n: int = 3,
    diversity_strength: float = 0.5,
) -> dict[str, Any]:
    """
    方向B：概念行业轮动选ETF（按ETF聚合平均动量）。

    计算每个概念过去N日累计涨幅，按ETF聚合取平均动量，
    从动量前N中按权重随机选，并对近期持仓施加惩罚。

    Args:
        concept_daily: 概念日线DataFrame，列: date, concept, close, return
        concept_map: {concept: (order_book_id, etf_name)} 映射
        trade_date: 当前交易日
        window: 动量窗口
        avoid_etfs: 需要施加动量惩罚的ETF集合（近期持仓）
        top_n: 候选数量
        diversity_strength: 避免集中化的惩罚强度（0=不惩罚，1=完全避免）

    Returns:
        {order_book_id, momentum=(avg_mom), max_momentum, etf_name, concept=(best_concept)}
    """
    trade_date = pd.Timestamp(trade_date).normalize()
    etf_map = build_etf_concept_map(concept_map)

    hist = concept_daily[concept_daily["date"] <= trade_date].copy()
    if hist.empty:
        oid, name = concept_map.get("5G概念", ("510050.XSHG", "上证50ETF"))
        return {"order_book_id": oid, "momentum": 0.0, "etf_name": name, "concept": ""}

    last_date = hist["date"].max()
    cutoff = last_date - pd.Timedelta(days=window * 2)
    recent = hist[hist["date"] >= cutoff].copy()

    # 1. 计算每个概念的动量
    concept_mom: dict[str, float] = {}
    for c in recent["concept"].unique():
        if c not in concept_map:
            continue
        cdata = recent[recent["concept"] == c].sort_values("date")
        if len(cdata) < window:
            continue
        if window == 1:
            if len(cdata) < 2:
                continue
            mom = cdata["close"].iloc[-1] / cdata["close"].iloc[-2] - 1
        else:
            mom = cdata["close"].iloc[-1] / cdata["close"].iloc[-window] - 1
        concept_mom[c] = mom

    if not concept_mom:
        oid, name = concept_map.get("5G概念", ("510050.XSHG", "上证50ETF"))
        return {"order_book_id": oid, "momentum": 0.0, "etf_name": name, "concept": ""}

    # 2. 按ETF聚合: 计算每个ETF下概念动量的平均值
    etf_avg_mom: dict[str, float] = {}
    etf_best_concept: dict[str, str] = {}
    etf_max_mom: dict[str, float] = {}
    ranked_candidates: list[tuple[str, float, str]] = []

    for oid, concepts in etf_map.items():
        moms = [concept_mom[c] for c in concepts if c in concept_mom]
        if not moms:
            continue
        avg_mom = sum(moms) / len(moms)
        max_mom = max(moms)
        etf_avg_mom[oid] = avg_mom
        etf_max_mom[oid] = max_mom
        best_c = max(concepts, key=lambda c: concept_mom.get(c, -float("inf")))
        etf_best_concept[oid] = best_c
        ranked_candidates.append((oid, avg_mom, best_c))

    if not etf_avg_mom:
        oid, name = concept_map.get("5G概念", ("510050.XSHG", "上证50ETF"))
        return {"order_book_id": oid, "momentum": 0.0, "etf_name": name, "concept": ""}

    # 2b. 对近期持仓施加动量惩罚
    if avoid_etfs and diversity_strength > 0:
        top_mom = max(etf_avg_mom.values())
        for i, (oid, avg_mom, best_c) in enumerate(ranked_candidates):
            if oid in avoid_etfs:
                penalty = top_mom * diversity_strength
                ranked_candidates[i] = (oid, avg_mom - penalty, best_c)

    # 3. 按修正后动量降序排列
    ranked_candidates.sort(key=lambda x: x[1], reverse=True)

    # 4. 从前N中按动量权重随机选
    best_oid, best_concept = _pick_weighted_top_n(ranked_candidates, top_n=top_n)
    best_avg_mom = etf_avg_mom.get(best_oid, 0.0)
    best_max_mom = etf_max_mom.get(best_oid, 0.0)

    # 从concept_map中获取etf_name
    name = concept_map.get(best_concept, ("", ""))[1]
    if not name:
        for _, n in concept_map.values():
            name = n
            break

    return {
        "order_book_id": best_oid,
        "momentum": round(best_avg_mom, 6),
        "max_momentum": round(best_max_mom, 6),
        "etf_name": name,
        "concept": best_concept,
    }

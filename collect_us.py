"""美股日线采集器（GitHub Actions，每个交易日收盘后跑两次）。

数据源：Yahoo Finance（yfinance，复权价，全部历史）；失败时退回 Stooq 免费 CSV。
每只标的一个文件：data/us/<TICKER>.csv，列：date,open,high,low,close,volume（已复权收盘价对齐）。
状态写到 data/us/heartbeat.json。
"""
from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent / "data" / "us"
DATA.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (research collector; paper trading)"}

# 资产配置类 ETF + 板块 ETF + 几只大盘股 + VIX
TICKERS = [
    # 核心资产类
    "SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "VNQ",
    "TLT", "IEF", "SHY", "BIL", "LQD", "HYG", "TIP",
    "GLD", "SLV", "DBC", "USO",
    # 11 个 SPDR 板块
    "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLC", "XLRE",
    # 大盘股（第二期个股策略用）
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
]
INDEXES = {"^VIX": "VIX"}      # Stooq 符号 -> 文件名
status: dict[str, str] = {}


def stooq(symbol: str) -> list[list[str]]:
    s = symbol.lower().replace("-", "-")
    url = f"https://stooq.com/q/d/l/?s={s}.us&i=d" if not symbol.startswith("^") else f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    text = r.text.strip()
    if not text.startswith("Date,") or "Exceeded" in text[:200]:
        raise RuntimeError(f"stooq refused: {text[:80]!r}")
    rows = []
    for row in csv.reader(io.StringIO(text)):
        if row and row[0] != "Date" and len(row) >= 5:
            vol = row[5] if len(row) > 5 and row[5] else "0"
            rows.append([row[0], row[1], row[2], row[3], row[4], vol])
    if len(rows) < 100:
        raise RuntimeError(f"stooq too short: {len(rows)} rows")
    return rows


def yahoo(symbol: str) -> list[list[str]]:
    import yfinance as yf  # 仅在退回时导入
    h = yf.Ticker(symbol).history(period="max", auto_adjust=True)
    if h.empty:
        raise RuntimeError("yahoo empty")
    rows = []
    for ts, r in h.iterrows():
        rows.append([ts.strftime("%Y-%m-%d"), f"{r['Open']:.4f}", f"{r['High']:.4f}", f"{r['Low']:.4f}", f"{r['Close']:.4f}", str(int(r.get("Volume", 0) or 0))])
    return rows


def write(name: str, rows: list[list[str]]):
    path = DATA / f"{name}.csv"
    merged: dict[str, list[str]] = {}
    if path.exists():
        with path.open() as f:
            rd = csv.reader(f); next(rd, None)
            for row in rd:
                if row:
                    merged[row[0]] = row
    before = len(merged)
    for row in rows:
        merged[row[0]] = row          # 全量覆盖：复权价会随分红变动，以最新为准
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        w.writerows(sorted(merged.values(), key=lambda r: r[0]))
    return len(merged) - before, sorted(merged)[-1]


def main():
    todo = [(t, t) for t in TICKERS] + list(INDEXES.items())
    for symbol, name in todo:
        try:
            try:
                rows = yahoo(symbol)          # Yahoo 为主（Stooq 对云端 IP 返回人机验证页）
                src = "yahoo"
            except Exception as e1:
                rows = stooq(symbol)
                src = f"stooq (yahoo: {e1})"
            added, last = write(name, rows)
            status[name] = f"ok {src} +{added} last={last}"
        except Exception as e:
            status[name] = f"fail {e}"
        time.sleep(0.5)
    hb = {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": status}
    (DATA / "heartbeat.json").write_text(json.dumps(hb, indent=1))
    print(json.dumps(hb, indent=1, ensure_ascii=False))
    fails = [k for k, v in status.items() if v.startswith("fail")]
    if len(fails) > len(todo) // 2:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

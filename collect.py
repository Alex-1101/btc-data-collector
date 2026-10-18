"""24 小时数据采集器（跑在 GitHub Actions 上，每 10 分钟一次，免费、无需服务器）。

每次运行把下面几类数据追加到 data/ 下的 CSV（自动去重）：
  btc_1m.csv    Kraken XBT/USD 1 分钟 K 线（每次拿最近 720 根 = 12 小时，10 分钟跑一次绰绰有余）
  btc_1h.csv    1 小时 K 线（最近 720 根 = 30 天）
  btc_1d.csv    日线（最近 720 根）
  btc_1w.csv    周线（Kraken 自 2013 起的全部历史）
  fng.csv       Alternative.me 恐惧贪婪指数（含 2018 起全部历史）
  funding.csv   Kraken Futures 永续合约资金费率 + 未平仓量快照（每次一条）
  heartbeat.json 最近一次运行时间、每个源成功与否

任何一个源失败都不影响其他源；失败写进 heartbeat.json。
"""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)
UA = {"User-Agent": "btc-strategy-lab-collector/1.0 (+paper trading research)"}
status: dict[str, str] = {}


def get(url: str, params: dict | None = None, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # 网络抖动重试
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"{url}: {last}")


def append_rows(path: Path, header: list[str], rows: list[list], key_idx: int = 0) -> int:
    """按第 key_idx 列去重后追加，保持升序。返回新增行数。"""
    existing: dict[str, list] = {}
    if path.exists():
        with path.open() as f:
            rd = csv.reader(f)
            hdr = next(rd, None)
            for row in rd:
                if row:
                    existing[row[key_idx]] = row
    before = len(existing)
    for row in rows:
        existing[str(row[key_idx])] = [str(x) for x in row]
    ordered = sorted(existing.values(), key=lambda r: float(r[key_idx]) if r[key_idx].replace(".", "", 1).isdigit() else r[key_idx])
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(ordered)
    return len(existing) - before


def kraken_ohlc(interval: int, name: str):
    try:
        j = get("https://api.kraken.com/0/public/OHLC", {"pair": "XBTUSD", "interval": interval})
        key = next(k for k in j["result"] if k != "last")
        candles = j["result"][key]
        if interval >= 60:
            candles = candles[:-1]  # 最后一根未收盘（分钟线无所谓，下次会覆盖）
        rows = [[c[0], c[1], c[2], c[3], c[4], c[6], c[7]] for c in candles]
        n = append_rows(DATA / f"{name}.csv", ["ts", "open", "high", "low", "close", "volume", "trades"], rows)
        status[name] = f"ok +{n}"
    except Exception as e:
        status[name] = f"fail {e}"


def fear_greed():
    try:
        path = DATA / "fng.csv"
        limit = 0 if not path.exists() else 10          # 第一次拿全部历史，之后只拿最近 10 天
        j = get("https://api.alternative.me/fng/", {"limit": limit, "format": "json"})
        rows = [[int(d["timestamp"]), int(d["value"]), d["value_classification"]] for d in j["data"]]
        n = append_rows(path, ["ts", "value", "label"], rows)
        status["fng"] = f"ok +{n}"
    except Exception as e:
        status["fng"] = f"fail {e}"


def kraken_funding():
    """Kraken Futures 公开行情：PF_XBTUSD 永续的资金费率、标记价、未平仓量。每次一条快照。"""
    try:
        j = get("https://futures.kraken.com/derivatives/api/v3/tickers")
        t = next(x for x in j["tickers"] if x.get("symbol", "").upper() == "PF_XBTUSD")
        now = int(datetime.now(timezone.utc).timestamp())
        row = [now, t.get("fundingRate"), t.get("fundingRatePrediction"), t.get("markPrice"), t.get("indexPrice"),
               t.get("openInterest"), t.get("vol24h")]
        n = append_rows(DATA / "funding.csv", ["ts", "funding_rate", "funding_rate_pred", "mark", "index", "open_interest", "vol24h"], [row])
        status["funding"] = f"ok +{n}"
    except Exception as e:
        status["funding"] = f"fail {e}"


def main():
    kraken_ohlc(1, "btc_1m")
    kraken_ohlc(60, "btc_1h")
    kraken_ohlc(1440, "btc_1d")
    if datetime.now(timezone.utc).hour % 6 == 0:      # 周线一天拿 4 次就够
        kraken_ohlc(10080, "btc_1w")
    fear_greed()
    kraken_funding()
    hb = {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": status}
    (DATA / "heartbeat.json").write_text(json.dumps(hb, indent=1))
    print(json.dumps(hb, indent=1))
    if all(v.startswith("fail") for v in status.values()):
        raise SystemExit(1)   # 全部失败才算任务失败，GitHub 会发邮件提醒


if __name__ == "__main__":
    main()

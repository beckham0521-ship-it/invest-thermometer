"""매매 기록 저장·계산 (판다스 없이 — 웹 프로그램과 매일 계산이 같이 씀).

저장: <데이터 폴더>/trades.csv   (서버: /opt/invest-thermometer, PC: local_data/)
평균 단가는 이동평균법(매수 때 평균 갱신, 매도는 평균 단가로 차감).
순투입 = 매수 금액 합 − 매도 금액 합  → 남은 투자금 = 계획 총액 − 순투입
"""
from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FIELDS = ["id", "date", "etf", "side", "qty", "price", "kind", "memo", "created_at"]
ETFS = {  # key -> (이름, 국내 ETF)
    "ndx": ("나스닥100", "TIGER 미국나스닥100"),
    "sox": ("반도체", "TIGER 미국필라델피아반도체나스닥"),
    "spx": ("S&P500", "KODEX 미국S&P500"),
}
KINDS = ["기초 보유", "정기", "추가(피라미딩)", "리밸런싱", "기타"]
_LOCK = threading.Lock()


def data_dir() -> Path:
    d = os.environ.get("THERMO_DATA")
    p = Path(d) if d else Path(__file__).resolve().parent / "local_data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _file() -> Path:
    return data_dir() / "trades.csv"


def load() -> list[dict]:
    f = _file()
    if not f.exists():
        return []
    with f.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["id"] = int(r["id"])
        r["qty"] = int(r["qty"])
        r["price"] = float(r["price"])
    return sorted(rows, key=lambda r: (r["date"], r["id"]))


def _save(rows: list[dict]) -> None:
    f = _file()
    tmp = f.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["date"], r["id"])):
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, f)


def validate(d: dict) -> dict:
    try:
        date = datetime.strptime(str(d.get("date", "")).strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError("날짜 형식이 아니에요 (YYYY-MM-DD)")
    etf = d.get("etf")
    if etf not in ETFS:
        raise ValueError("종목을 골라 주세요")
    side = d.get("side")
    if side not in ("buy", "sell"):
        raise ValueError("매수/매도를 골라 주세요")
    try:
        qty = int(str(d.get("qty", "")).replace(",", ""))
        price = float(str(d.get("price", "")).replace(",", ""))
    except ValueError:
        raise ValueError("수량·단가는 숫자로 입력해 주세요")
    if qty <= 0 or price <= 0:
        raise ValueError("수량·단가는 0보다 커야 해요")
    kind = d.get("kind") if d.get("kind") in KINDS else "기타"
    memo = str(d.get("memo", "")).strip()[:200]
    return {"date": date, "etf": etf, "side": side, "qty": qty, "price": price, "kind": kind, "memo": memo}


def add(d: dict) -> dict:
    v = validate(d)
    with _LOCK:
        rows = load()
        v["id"] = max([r["id"] for r in rows], default=0) + 1
        v["created_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        _check_no_oversell(rows + [v])
        rows.append(v)
        _save(rows)
    return v


def update(tid: int, d: dict) -> dict:
    v = validate(d)
    with _LOCK:
        rows = load()
        old = next((r for r in rows if r["id"] == tid), None)
        if old is None:
            raise KeyError(tid)
        v["id"], v["created_at"] = tid, old.get("created_at", "")
        new = [v if r["id"] == tid else r for r in rows]
        _check_no_oversell(new)
        _save(new)
    return v


def delete(tid: int) -> None:
    with _LOCK:
        rows = load()
        new = [r for r in rows if r["id"] != tid]
        if len(new) == len(rows):
            raise KeyError(tid)
        _check_no_oversell(new)
        _save(new)


def _check_no_oversell(rows: list[dict]) -> None:
    held = {k: 0 for k in ETFS}
    for r in sorted(rows, key=lambda r: (r["date"], r["id"])):
        held[r["etf"]] += r["qty"] if r["side"] == "buy" else -r["qty"]
        if held[r["etf"]] < 0:
            raise ValueError(f"{r['date']} {ETFS[r['etf']][0]}: 보유 수량보다 많이 매도하게 돼요")


def split_months(remaining: float, monthly: float = 750_000) -> tuple[int, float]:
    """남은 투자금 = 월 적립액 × 개월(몫) + α(나머지)."""
    n = int(remaining // monthly) if monthly > 0 else 0
    return n, remaining - n * monthly


def summary(rows: list[dict] | None = None, prices: dict | None = None, plan_total: float = 30_000_000,
            monthly: float = 750_000) -> dict:
    rows = load() if rows is None else rows
    prices = prices or {}
    pos = {k: {"qty": 0, "cost": 0.0, "realized": 0.0, "bought": 0.0, "sold": 0.0} for k in ETFS}
    for r in sorted(rows, key=lambda r: (r["date"], r["id"])):
        p, amt = pos[r["etf"]], r["qty"] * r["price"]
        if r["side"] == "buy":
            p["qty"] += r["qty"]
            p["cost"] += amt
            p["bought"] += amt
        else:
            avg = p["cost"] / p["qty"] if p["qty"] else 0.0
            p["cost"] -= avg * r["qty"]
            p["qty"] -= r["qty"]
            p["realized"] += (r["price"] - avg) * r["qty"]
            p["sold"] += amt
    total_value = 0.0
    for k, p in pos.items():
        p["avg"] = p["cost"] / p["qty"] if p["qty"] else 0.0
        p["price"] = prices.get(k)
        p["value"] = p["qty"] * p["price"] if p["price"] else None
        p["pl"] = p["value"] - p["cost"] if p["value"] is not None else None
        p["pl_pct"] = (p["pl"] / p["cost"] * 100) if p["pl"] is not None and p["cost"] else None
        total_value += p["value"] or 0.0
    for p in pos.values():
        p["weight"] = (p["value"] / total_value * 100) if total_value and p["value"] is not None else None
    net = sum(p["bought"] - p["sold"] for p in pos.values())
    cost = sum(p["cost"] for p in pos.values())
    return {"positions": pos, "total_value": total_value, "total_cost": cost,
            "total_pl": total_value - cost if total_value else None,
            "realized": sum(p["realized"] for p in pos.values()),
            "net_invested": net, "plan_total": plan_total, "remaining": max(0.0, plan_total - net),
            "monthly": monthly, "remaining_months": split_months(max(0.0, plan_total - net), monthly)[0],
            "remaining_alpha": split_months(max(0.0, plan_total - net), monthly)[1],
            "count": len(rows), "has_base": any(r["kind"] == "기초 보유" for r in rows)}


def save_prices(prices: dict, date: str) -> None:
    (data_dir() / "kr_prices.json").write_text(json.dumps({"date": date, "prices": prices}, ensure_ascii=False))


def load_prices() -> tuple[dict, str]:
    f = data_dir() / "kr_prices.json"
    if not f.exists():
        return {}, ""
    j = json.loads(f.read_text())
    return j.get("prices", {}), j.get("date", "")

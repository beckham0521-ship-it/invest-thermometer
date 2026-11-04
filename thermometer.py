"""
투자온도계 (Investment Thermometer)
미국장 마감 종가 기준으로 아래 지표를 수집/계산합니다.

  1. NAS100 종가        : ^NDX (나스닥100 지수, NAS100USD CFD가 추종하는 기초지수)
     전고점 대비 하락률  : 그날까지의 역대 최고 종가 대비 %
  2. 공포탐욕지수        : CNN Fear & Greed Index
  3. RSI(14) 주간       : 나스닥100 주봉 종가
  4. RSI(14) 일간       : 나스닥100 일봉 종가
  5. Slow Stochastic    : 일봉 기준 (14, 3, 3)  -> Slow %K, Slow %D

온도(0~100) = 공포탐욕 / 주간RSI / 일간RSI / Slow %K 의 단순평균

저장
  history_full.csv : 모든 거래일 원본 (지우지 않음)
  history.csv      : 정리 규칙 적용본 (대시보드에 표시되는 기록)
                     - 이번 달          : 매일
                     - 지난달, 지지난달  : 매주 토요일 아침에 얻은 값 (= 그 주 마지막 거래일, 보통 금요일 종가)
                     - 그 이전          : 월마다 최저 온도 하루

사용법
  python thermometer.py                     # 마지막 기록 이후 빠진 날 + 오늘 채우기
  python thermometer.py --since 2026-01-01  # 지정 날짜부터 다시 채우기
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

BASE = Path(__file__).resolve().parent
FULL = BASE / "history_full.csv"
HISTORY = BASE / "history.csv"
TEMPLATE = BASE / "template.html"
DASHBOARD = BASE / "dashboard.html"
TICKER = "^NDX"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ---------- 지표 계산 ----------
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (TradingView 기본 RSI와 동일 방식)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return 100 - 100 / (1 + avg_gain / avg_loss)


def slow_stoch(df: pd.DataFrame, k: int = 14, smooth: int = 3, d: int = 3):
    """Slow Stochastic: Fast %K(14) -> SMA3 = Slow %K -> SMA3 = Slow %D."""
    low_min = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    fast_k = 100 * (df["Close"] - low_min) / (high_max - low_min)
    slow_k = fast_k.rolling(smooth).mean()
    return slow_k, slow_k.rolling(d).mean()


# ---------- 데이터 수집 ----------
def fetch_ndx() -> pd.DataFrame:
    df = yf.download(TICKER, period="max", interval="1d", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise RuntimeError("나스닥100 데이터를 가져오지 못했습니다.")
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def fetch_fear_greed(since: str) -> dict[str, tuple[float, str]]:
    """날짜(YYYY-MM-DD) -> (점수, 등급). 같은 날짜가 여러 개면 마지막 값."""
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{since}"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        out = {}
        for p in r.json()["fear_and_greed_historical"]["data"]:
            day = datetime.utcfromtimestamp(p["x"] / 1000).date().isoformat()
            out[day] = (round(float(p["y"]), 1), p.get("rating"))
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 공포탐욕지수 수집 실패: {e}", file=sys.stderr)
        return {}


# ---------- 해석 ----------
def label(temp: float) -> str:
    if temp >= 80:
        return "과열 (Extreme Greed)"
    if temp >= 60:
        return "따뜻함 (Greed)"
    if temp >= 40:
        return "중립 (Neutral)"
    if temp >= 20:
        return "서늘함 (Fear)"
    return "냉각 (Extreme Fear)"


def build_rows(df: pd.DataFrame, dates: list[pd.Timestamp], fg: dict) -> list[dict]:
    daily_rsi = rsi(df["Close"])
    slow_k, slow_d = slow_stoch(df)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")  # 한국시간
    rows = []
    for d in dates:
        # 주간 RSI: 그날까지의 데이터로 주봉을 만든다 (진행 중인 주는 그날 종가 반영)
        weekly = df["Close"].loc[:d].resample("W-FRI").last().dropna()
        w_rsi = float(rsi(weekly).iloc[-1])
        key = d.date().isoformat()
        fg_score, fg_rating = fg.get(key, (None, None))
        parts = [w_rsi, float(daily_rsi[d]), float(slow_k[d])]
        if fg_score is not None:
            parts.append(fg_score)
        temp = sum(parts) / len(parts)
        closes = df["Close"].loc[:d]
        ath_date = closes.idxmax()
        ath = float(closes[ath_date])
        rows.append({
            "date": key,
            "nas100_close": round(float(df.at[d, "Close"]), 2),
            "drawdown_pct": round((float(df.at[d, "Close"]) / ath - 1) * 100, 2),
            "ath_close": round(ath, 2),
            "ath_date": ath_date.date().isoformat(),
            "fear_greed": fg_score,
            "fear_greed_rating": fg_rating,
            "rsi_weekly": round(w_rsi, 2),
            "rsi_daily": round(float(daily_rsi[d]), 2),
            "slow_k": round(float(slow_k[d]), 2),
            "slow_d": round(float(slow_d[d]), 2),
            "temperature": round(temp, 1),
            "status": label(temp),
            "updated_at": now,
        })
    return rows


# ---------- 기록 정리 ----------
def compact(full: pd.DataFrame) -> pd.DataFrame:
    """이번 달=매일, 지난달·지지난달=주마다 마지막 거래일(토요일 아침 값), 그 이전=월별 최저."""
    h = full.copy()
    dt = pd.to_datetime(h["date"])
    h["_m"] = dt.dt.to_period("M")
    h["_w"] = dt.dt.to_period("W-FRI")
    cur = h["_m"].max()

    now = h[h["_m"] == cur].assign(kind="daily")
    weekly_last = h.loc[h.groupby("_w")["date"].idxmax()]  # 주마다 마지막 거래일
    mid = weekly_last[(weekly_last["_m"] < cur) & (weekly_last["_m"] >= cur - 2)].assign(kind="weekly")
    old = h[h["_m"] < cur - 2]
    old = old.loc[old.groupby("_m")["temperature"].idxmin()].assign(kind="monthly_min")

    out = pd.concat([old, mid, now]).drop(columns=["_m", "_w"]).sort_values("date")
    return out.reset_index(drop=True)


def render_dashboard(hist: pd.DataFrame) -> None:
    rows = json.loads(hist.to_json(orient="records", force_ascii=False))
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/[]", json.dumps(rows, ensure_ascii=False)
    )
    DASHBOARD.write_text(html, encoding="utf-8")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 작업 스케줄러 실행 시 인코딩 오류 방지
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="이 날짜부터 다시 채우기 (YYYY-MM-DD)")
    args = ap.parse_args()

    full = pd.read_csv(FULL) if FULL.exists() else pd.DataFrame()
    df = fetch_ndx()

    if args.since:
        start = pd.Timestamp(args.since)
    elif not full.empty:
        start = pd.Timestamp(full["date"].max())  # 마지막 날도 다시 계산(최종값 갱신)
    else:
        start = df.index[-1]
    dates = [d for d in df.index if d >= start]

    fg = fetch_fear_greed((start - pd.Timedelta(days=7)).date().isoformat())
    # 공포탐욕 수집이 실패한 날은 이전에 저장해 둔 값을 유지
    if not full.empty:
        for _, r in full.dropna(subset=["fear_greed"]).iterrows():
            fg.setdefault(r["date"], (float(r["fear_greed"]), r["fear_greed_rating"]))
    new = pd.DataFrame(build_rows(df, dates, fg))

    if not full.empty:
        full = full[~full["date"].isin(new["date"])]
    full = pd.concat([full, new], ignore_index=True).sort_values("date").reset_index(drop=True)
    full.to_csv(FULL, index=False, encoding="utf-8-sig")

    hist = compact(full)
    hist.to_csv(HISTORY, index=False, encoding="utf-8-sig")
    render_dashboard(hist)

    row = full.iloc[-1]
    print(f"\n===== 투자온도계  {row['date']} (미국장 종가 기준) =====")
    print(f" 1. NAS100 종가        : {row['nas100_close']:,.2f}")
    print(f"    전고점             : {row['ath_close']:,.2f}  ({row['ath_date']})")
    print(f"    전고점 대비 하락률  : {row['drawdown_pct']:+.2f}%")
    fg_txt = f"{row['fear_greed']} ({row['fear_greed_rating']})" if pd.notna(row["fear_greed"]) else "수집 실패"
    print(f" 2. 공포탐욕지수        : {fg_txt}")
    print(f" 3. RSI(14) 주간       : {row['rsi_weekly']}")
    print(f" 4. RSI(14) 일간       : {row['rsi_daily']}")
    print(f" 5. Slow %K(14,3)      : {row['slow_k']}")
    print("-" * 46)
    print(f" 🌡  온도 {row['temperature']}°  →  {row['status']}")
    print(f" 이번에 계산한 거래일: {len(new)}일 / 원본 {len(full)}일 / 표시 {len(hist)}개")
    print(f" 대시보드: {DASHBOARD}\n")


if __name__ == "__main__":
    main()

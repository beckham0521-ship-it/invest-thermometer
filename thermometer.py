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

피라미딩 매수 점수 (총 30점)
  RSI(일간)      40 이하 +1 / 35 이하 +2
  Slow %K        20 이하 +1 / 10 이하 +2
  공포탐욕        30 이하 +1 / 10 이하 +2
  이동평균선      종가가 해당 선 이하 = 도달. 도달한 선 중 가장 높은 점수 하나만
                 60일 +1 / 120일 +3 / 200일 +6 / 60주 +9 / 120주 +12 / 200주 +16
  VIX            30 이상 +2 / 40 이상 +5 / 50 이상 +8
  총점 -> 추가 매수 개월분: 1~3=1, 4~6=2, 7~9=3, 10~13=4, 14~18=5, 19~24=6, 25~30=7~12

저장
  history_full.csv : 모든 거래일 원본 (지우지 않음)
  history.csv      : 정리 규칙 적용본 (대시보드에 표시되는 기록)
                     - 이번 달          : 매일
                     - 지난달, 지지난달  : 매주 토요일 아침에 얻은 값 (= 그 주 마지막 거래일, 보통 금요일 종가)
                     - 그 이전          : 월마다 피라미딩 점수가 가장 높은 하루 (같으면 하락률이 가장 큰 날)

지수 (INDEXES)
  ndx 나스닥100 ^NDX (QQQ) / sox 반도체 ^SOX (SOXX) / spx S&P500 ^GSPC (VOO)  — 탭·메시지 순서
  공포탐욕·VIX는 시장 전체 지표라 세 지수 공통. 같은 점수 기준을 쓰며 2011~ 검증으로 확인.
  결과 페이지: site/index.html, site/sox.html, site/spx.html (GitHub Pages로 그대로 배포)

사용법
  python thermometer.py                     # 마지막 기록 이후 빠진 날 + 오늘 채우기 (새 지수는 2026-01-01부터)
  python thermometer.py --since 2026-01-01  # 지정 날짜부터 다시 채우기
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

BASE = Path(__file__).resolve().parent
FULL = BASE / "history_full.csv"
HISTORY = BASE / "history.csv"
TEMPLATE = BASE / "template.html"
SITE = BASE / "site"
BACKFILL_START = "2026-01-01"
PAGE_URL = "https://beckham0521-ship-it.github.io/invest-thermometer/"

INDEXES = [
    # slow: 적립 조건 Slow 기준 / wl, wl2: RSI 주간 저점 1·2단계 / wh_stop, wh_trim: RSI 주간 고점(추가 매수 멈춤 / 일부 실현)
    {"key": "ndx", "tab": "QQQ", "name": "나스닥100", "short": "NAS100", "ticker": "^NDX", "etf": "QQQ",
     "full": "history_full.csv", "hist": "history.csv", "page": "index.html",
     "slow": 20, "fg": 15, "wl": 40, "wl2": 35, "wh_stop": 67, "wh_trim": 70, "triple": "",
     "low1": ["warn", "⚠ 분할 매수", "하락이 길어질 수 있어 3~4주에 나눠서 (검증: 이후 6개월 상승확률 47~60%)"],
     "low2": ["warn", "⚠ 분할 매수 · 비중 확대", "1년 성과는 좋았지만(+6~10%p) 6개월 상승확률은 38~46%라 반드시 나눠서"],
     "note": "2011~2026 나스닥100 검증: 적립 조건은 Slow<20 · RSI일 30~40 · 공탐<15 (범위를 좁힐수록 ★★ 날 성과 개선) · 추가 매수 금액은 피라미딩 점수 · RSI 주간 ≤ 40은 하락이 길어질 수 있어 분할 매수 · RSI 주간 ≥ 70부터 이후 3개월 성과가 약해 일부 실현"},
    {"key": "sox", "tab": "SOXX", "name": "필라델피아 반도체", "short": "SOX", "ticker": "^SOX", "etf": "SOXX",
     "full": "history_full_sox.csv", "hist": "history_sox.csv", "page": "sox.html",
     "slow": 10, "fg": 20, "wl": 40, "wl2": 35, "wh_stop": 75, "wh_trim": 78,
     "triple": "반도체는 ★★★ 날이 급락 한가운데인 경우가 많았음 (이후 1년 평균보다 3~6%p 낮음) → 2~3번 나눠서",
     "low1": ["buy", "적극 매수 구간", "반도체는 RSI 주간 40 이하 이후 반등이 컸음 (검증: 1년 상승확률 92~94%)"],
     "low2": ["buy", "최대 매수 구간", "RSI 주간 35 이하 이후 1년 상승확률 100% (검증: 평균보다 +33~43%p)"],
     "note": "2011~2026 반도체 검증: 변동성이 커서 Slow는 10 미만일 때만 적립 조건으로 인정 · RSI 주간 ≤ 40 적극 매수, ≤ 35 최대 매수 · 상승 추세가 강해 RSI 주간 78 이상에서만 일부 실현"},
    {"key": "spx", "tab": "VOO", "name": "S&P500", "short": "S&P500", "ticker": "^GSPC", "etf": "VOO",
     "full": "history_full_spx.csv", "hist": "history_spx.csv", "page": "spx.html",
     "slow": 20, "fg": 15, "wl": 40, "wl2": 35, "wh_stop": 67, "wh_trim": 70, "triple": "",
     "low1": ["buy", "적극 매수 구간", "S&P500은 RSI 주간 40 이하 이후 성과가 좋았음 (검증: 1년 상승확률 87~93%)"],
     "low2": ["buy", "최대 매수 구간", "RSI 주간 35 이하 이후 1년 상승확률 100% (검증: 평균보다 +15~17%p)"],
     "note": "2011~2026 S&P500 검증: 적립 조건은 현재 기준 유지 · RSI 주간 ≤ 40 적극 매수, ≤ 35 최대 매수 · RSI 주간 ≥ 70 이후 1년 성과가 평균보다 5~9%p 낮아 세 지수 중 수익 실현 신호가 가장 잘 맞음"},
]
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
FG_BACKUP_URL = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"
WARNINGS: list[str] = []  # 오늘 값 확인용 경고 (메시지·대시보드에 표시)


def with_retry(fn, what: str, tries: int = 3):
    """실패하면 다시 시도. GitHub Actions에서는 60초, PC에서는 5초 간격."""
    wait = 60 if os.environ.get("CI") else 5
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            print(f"[재시도] {what} 실패 {i}/{tries}: {type(e).__name__}: {e}", file=sys.stderr)
            if i == tries:
                raise
            time.sleep(wait)


def fetch_ndx() -> pd.DataFrame:
    return fetch_index("^NDX")


def _download(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="max", interval="1d", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise RuntimeError(f"{ticker} 데이터가 비어 있음")
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def fetch_index(ticker: str) -> pd.DataFrame:
    return with_retry(lambda: _download(ticker), f"{ticker} 가격")


def fetch_vix() -> pd.Series:
    try:
        return with_retry(lambda: _download("^VIX"), "VIX")["Close"]
    except Exception:  # noqa: BLE001
        return pd.Series(dtype=float)


def _fg_cnn(since: str) -> dict:
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{since}"
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    out = {}
    for p in r.json()["fear_and_greed_historical"]["data"]:
        day = datetime.fromtimestamp(p["x"] / 1000, timezone.utc).date().isoformat()
        out[day] = (round(float(p["y"]), 1), p.get("rating"))
    if not out:
        raise RuntimeError("CNN 응답에 데이터 없음")
    return out


def fetch_fear_greed(since: str) -> dict[str, tuple[float, str]]:
    """CNN 공포탐욕지수. 날짜(YYYY-MM-DD) -> (점수, 등급). 실패하면 빈 dict."""
    try:
        return with_retry(lambda: _fg_cnn(since), "CNN 공포탐욕")
    except Exception:  # noqa: BLE001
        return {}


def fetch_fear_greed_backup() -> dict[str, tuple[float, str]]:
    """대체 출처: CNN 값을 매일 모아 공개하는 GitHub 데이터 (whit3rabbit/fear-greed-data)."""
    def get():
        r = requests.get(FG_BACKUP_URL, headers=UA, timeout=20)
        r.raise_for_status()
        out = {}
        for line in r.text.splitlines()[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 2 and parts[1]:
                out[parts[0]] = (round(float(parts[1]), 1), parts[2] if len(parts) > 2 else None)
        if not out:
            raise RuntimeError("대체 출처 데이터 없음")
        return out
    try:
        return with_retry(get, "공포탐욕 대체 출처")
    except Exception:  # noqa: BLE001
        return {}


def latest_us_trading_day() -> str:
    """미국 동부 기준 오늘(주말이면 직전 금요일). 휴장일은 고려하지 않음."""
    et = datetime.now(timezone(timedelta(hours=-5)))
    d = et.date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


# ---------- 피라미딩 매수 점수 ----------
MA_LEVELS = [  # (키, 이름, 점수)  — 점수 오름차순
    ("ma60d", "60일선", 1), ("ma120d", "120일선", 3), ("ma200d", "200일선", 6),
    ("ma60w", "60주선", 9), ("ma120w", "120주선", 12), ("ma200w", "200주선", 16),
]


def pts_rsi(v):
    return 0 if v is None else 2 if v <= 35 else 1 if v <= 40 else 0


def pts_stoch(v):
    return 0 if v is None else 2 if v <= 10 else 1 if v <= 20 else 0


def pts_fg(v):
    return 0 if v is None else 2 if v <= 10 else 1 if v <= 30 else 0


def pts_vix(v):
    return 0 if v is None else 8 if v >= 50 else 5 if v >= 40 else 2 if v >= 30 else 0


def buy_months(score: int) -> int:
    if score <= 0:
        return 0
    for hi, m in [(3, 1), (6, 2), (9, 3), (13, 4), (18, 5), (24, 6)]:
        if score <= hi:
            return m
    return min(12, score - 18)


def buy_zone(score: int) -> str:
    if score <= 0:
        return "신호 없음"
    if score <= 9:
        return "흔한 조정"
    if score <= 24:
        return "깊은 조정"
    return "공포 구간"


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


def build_rows(df: pd.DataFrame, dates: list[pd.Timestamp], fg: dict, vix: pd.Series) -> list[dict]:
    daily_rsi = rsi(df["Close"])
    ma_d = {n: df["Close"].rolling(n).mean() for n in (60, 120, 200)}
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

        # 피라미딩 점수
        close = float(df.at[d, "Close"])
        mas = {f"ma{n}d": ma_d[n][d] for n in (60, 120, 200)}
        mas.update({f"ma{n}w": weekly.rolling(n).mean().iloc[-1] for n in (60, 120, 200)})
        mas = {k: (None if pd.isna(v) else round(float(v), 2)) for k, v in mas.items()}
        ma_hit = [(name, p) for k, name, p in MA_LEVELS if mas[k] is not None and close <= mas[k]]
        ma_name, ma_pts = max(ma_hit, key=lambda x: x[1]) if ma_hit else (None, 0)
        v = vix.loc[:d]
        vix_v = round(float(v.iloc[-1]), 2) if len(v) else None
        p_rsi, p_sto = pts_rsi(float(daily_rsi[d])), pts_stoch(float(slow_k[d]))
        p_fg, p_vix = pts_fg(fg_score), pts_vix(vix_v)
        score = p_rsi + p_sto + p_fg + ma_pts + p_vix

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
            "vix": vix_v,
            **mas,
            "ma_level": ma_name,
            "pts_rsi": p_rsi, "pts_stoch": p_sto, "pts_fg": p_fg, "pts_ma": ma_pts, "pts_vix": p_vix,
            "buy_score": score,
            "buy_months": buy_months(score),
            "buy_zone": buy_zone(score),
            "updated_at": now,
        })
    return rows


# ---------- 기록 정리 ----------
def compact(full: pd.DataFrame) -> pd.DataFrame:
    """이번 달=매일, 지난달·지지난달=주마다 마지막 거래일(토요일 아침 값), 그 이전=월별 최고 점수일."""
    h = full.copy()
    dt = pd.to_datetime(h["date"])
    h["_m"] = dt.dt.to_period("M")
    h["_w"] = dt.dt.to_period("W-FRI")
    cur = h["_m"].max()

    now = h[h["_m"] == cur].assign(kind="daily")
    weekly_last = h.loc[h.groupby("_w")["date"].idxmax()]  # 주마다 마지막 거래일
    mid = weekly_last[(weekly_last["_m"] < cur) & (weekly_last["_m"] >= cur - 2)].assign(kind="weekly")
    old = h[h["_m"] < cur - 2]
    old = (old.sort_values(["buy_score", "drawdown_pct", "date"], ascending=[False, True, True])
              .groupby("_m").head(1).assign(kind="monthly_min"))

    out = pd.concat([old, mid, now]).drop(columns=["_m", "_w"]).sort_values("date")
    return out.reset_index(drop=True)


def monthly_best(full: pd.DataFrame) -> pd.DataFrame:
    """월마다 매수 점수가 가장 높은 날 (같으면 하락률이 가장 큰 날). 최근 12개월."""
    h = full.dropna(subset=["buy_score"]).copy()
    h["_m"] = h["date"].str[:7]
    best = (h.sort_values(["buy_score", "drawdown_pct", "date"], ascending=[False, True, True])
             .groupby("_m").head(1).drop(columns="_m"))
    return best.sort_values("date").tail(12)


def render_page(ix: dict, hist: pd.DataFrame, monthly: pd.DataFrame, full: pd.DataFrame) -> None:
    def js(df):
        return json.dumps(json.loads(df.to_json(orient="records", force_ascii=False)), ensure_ascii=False)

    tabs = "".join(
        f'<a href="{o["page"]}" class="{"on" if o["key"] == ix["key"] else ""}">{o["tab"]}</a>' for o in INDEXES)
    cfg = {k: ix[k] for k in ("slow", "fg", "triple", "wl", "wl2", "wh_stop", "wh_trim", "low1", "low2", "note")}
    cfg["warn"] = WARNINGS
    cfg["data_date"] = str(full["date"].max())
    html = (TEMPLATE.read_text(encoding="utf-8-sig")
            .replace("/*__DATA__*/[]", js(hist))
            .replace("/*__MONTHLY__*/[]", js(monthly))
            .replace("/*__FULL__*/[]", js(full.drop(columns=["updated_at"], errors="ignore")))
            .replace("/*__CFG__*/{}", json.dumps(cfg, ensure_ascii=False))
            .replace("<!--__TABS__-->", tabs)
            .replace("__INDEX_NAME__", ix["name"]).replace("__INDEX_SHORT__", ix["short"])
            .replace("__ETF__", ix["etf"]).replace("__SLOW__", str(ix["slow"])).replace("__FG__", str(ix["fg"])))
    SITE.mkdir(exist_ok=True)
    (SITE / ix["page"]).write_text(html, encoding="utf-8")


def _f(v, d=1):
    return "-" if pd.isna(v) else f"{v:.{d}f}"


def todo_lines(ix: dict, r: pd.Series, n: int, ctx: dict) -> list[str]:
    """전략 메시지 규칙대로 오늘 할 일."""
    out = []
    rw, months = r["rsi_weekly"], int(r["buy_months"])
    day = _today_kst().day
    if ctx.get("rebal"):
        out.append("🔄 리밸런싱 주간: 맨 아래 내 IRP 칸 수량대로 매도·매수 먼저")
    # 1) 수익 실현 / 멈춤
    if rw >= ix["wh_trim"]:
        out.append("수익 실현: 평가 수익 30% 내외 매도 고려 (IRP 안이라 세금 없음) · 새 매수 멈춤")
    elif rw >= ix["wh_stop"]:
        out.append("추가 매수 멈춤 · 정기 적립만")
    # 2) 하락 구간 추가 매수 (당겨쓰기)
    if rw < ix["wh_stop"] and months >= 2:
        if n == 3 and ix.get("triple"):
            how = "급락 중일 수 있어 2~3번 나눠서"
        elif rw <= ix["wl"] and ix["low1"][0] == "warn":
            how = "하락이 길어질 수 있어 3~4주에 나눠서"
        elif rw <= ix["wl"]:
            how = "적극 매수 구간이라 이번 주 안에"
        else:
            how = "이번 주 안에"
        out.append(f"추가 매수: 이번 하락 구간에 {months}개월분까지 채우기 (이미 당겨 산 만큼 빼고) → {how}")
    # 3) 정기 적립
    if ix["key"] in ctx.get("rest", set()):
        out.append(f"정기 적립: {ctx.get('prio_name', '')} 우선 기간이라 쉬기")
    elif ctx.get("done"):
        out.append("정기 적립: 이번 달 완료 → 다음 달 ★★ 날 기다리기")
    elif n >= 2:
        out.append("정기 적립: <b>오늘 매수</b> (★★ 좋은 날)")
    elif n == 1 and day >= 20:
        out.append("정기 적립: 이번 달 ★★ 날이 없었으면 오늘 매수")
    elif n == 0 and day >= 24:
        out.append("정기 적립: 월말이라 이번 주 안에 매수")
    else:
        out.append("정기 적립: ★★ 날 기다리기")
    return out


def index_block(ix: dict, r: pd.Series, full: pd.DataFrame, latest: str | None = None,
                ctx: dict | None = None) -> str:
    ctx = ctx or {}
    met = []
    if r["slow_k"] < ix["slow"]:
        met.append("Slow")
    if 30 <= r["rsi_daily"] <= 40:
        met.append("RSI일")
    if pd.notna(r["fear_greed"]) and r["fear_greed"] < ix["fg"]:
        met.append("공탐")
    n = len(met)
    stars = "★" * n + "☆" * (3 - n)
    dca = (f"{stars} 좋은 날 ({' · '.join(met)})" if n >= 2
           else f"{stars} 보통 ({met[0]}만 충족)" if n == 1 else f"{stars} 대기")
    if n == 3 and ix.get("triple"):
        dca += f"\n  ⚠ {ix['triple']}"
    months, score = int(r["buy_months"]), int(r["buy_score"])
    add = f"{months}개월분 ({score}점 · {r['buy_zone']})" if months else f"없음 ({score}점)"
    rw = r["rsi_weekly"]
    if rw <= ix["wl2"]:
        bear = f"RSI주 ≤ {ix['wl2']} → {ix['low2'][1]}"
    elif rw <= ix["wl"]:
        bear = f"RSI주 ≤ {ix['wl']} → {ix['low1'][1]}"
    else:
        bear = "해당 없음"
    if rw >= ix["wh_trim"]:
        sell = f"RSI주 ≥ {ix['wh_trim']} → 수익 30% 내외 실현 고려"
    elif rw >= ix["wh_stop"]:
        sell = f"RSI주 ≥ {ix['wh_stop']} → 추가 매수 멈춤"
    else:
        sell = "해당 없음"
    best = ""
    mon = full[full["date"].str[:7] == r["date"][:7]].dropna(subset=["buy_score"])
    if len(mon):
        b = mon.sort_values(["buy_score", "drawdown_pct", "date"], ascending=[False, True, True]).iloc[0]
        dow = "월화수목금토일"[pd.Timestamp(b["date"]).day_of_week]
        bm = int(b["buy_months"])
        best = (f"• 이번 달 최고점: {b['date'][5:].replace('-', '/')}({dow}) "
                f"{int(b['buy_score'])}점 · {f'{bm}개월분' if bm else '추가 매수 없음'}\n")
    ma = r["ma_level"] if isinstance(r["ma_level"], str) else "도달 없음"
    name, etf, short = (_html.escape(ix[k]) for k in ("name", "etf", "short"))  # S&P 의 & 처리
    todo = "".join(f" · {t}\n" for t in todo_lines(ix, r, n, ctx))
    return (
        f"<b>📈 {name}</b> ({etf})"
        + (f" ⚠ {r['date'][5:].replace('-', '/')} 값" if latest and r["date"] < latest else "") + "\n"
        f"👉 <b>오늘 할 일</b>\n{todo}"
        f"• 정기 적립: {dca}\n"
        f"• 추가 매수: <b>{add}</b>\n"
        f"• 하락장: {bear}\n"
        f"• 수익 실현: {sell}\n"
        f"{best}"
        f"{short} {r['nas100_close']:,.0f} (전고점 대비 {r['drawdown_pct']:+.1f}%)\n"
        f"RSI 일 {_f(r['rsi_daily'])} (별 30~40 · 점수 ≤40/≤35)\n"
        f"RSI 주 {_f(rw)} (하락장 ≤{ix['wl']}/≤{ix['wl2']} · 실현 ≥{ix['wh_stop']}/≥{ix['wh_trim']})\n"
        f"Slow {_f(r['slow_k'])} (별 &lt;{ix['slow']} · 점수 ≤20/≤10)\n"
        f"공탐 {_f(r['fear_greed'])} (별 &lt;{ix['fg']} · 점수 ≤30/≤10)\n"
        f"이평선 {ma} (+{int(r['pts_ma'])}점)\n"
        f'<a href="{PAGE_URL}{"" if ix["page"] == "index.html" else ix["page"]}">대시보드 열기</a>'
    )


# ---------- 내 IRP (텔레그램 전용, 공개 페이지·로그에 절대 출력하지 않음) ----------
KR_ETF = {  # 지수 key -> (야후 티커, 이름)
    "ndx": ("133690.KS", "나스닥100"),
    "sox": ("381180.KS", "반도체"),
    "spx": ("379800.KS", "S&amp;P500"),
}


def _man(x: float) -> str:
    return f"{x / 1e4:,.1f}만"


def _kr_price(tk: str) -> tuple[float, str]:
    def get():
        d = yf.download(tk, period="10d", interval="1d", auto_adjust=False, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        c = d["Close"].dropna()
        if c.empty:
            raise RuntimeError(f"{tk} 가격 없음")
        return float(c.iloc[-1]), c.index[-1].strftime("%m/%d")
    return with_retry(get, f"{tk} 국내 ETF")


def _today_kst():
    """오늘 날짜(KST). 시험용으로 THERMO_TODAY=YYYY-MM-DD 로 바꿀 수 있음."""
    t = os.environ.get("THERMO_TODAY")
    return datetime.strptime(t, "%Y-%m-%d").date() if t else datetime.now(KST).date()


def next_rebalance(today, first: str, month: int):
    """다음 리밸런싱 주 시작일 (그 달 1~7일). first='2027-03' 이 첫 시행, 이후 매년 month월."""
    fy, fm = map(int, first.split("-"))
    first_d = today.replace(year=fy, month=fm, day=1)
    if today <= first_d.replace(day=7):
        return first_d
    y = today.year
    cand = today.replace(year=y, month=month, day=1)
    if cand <= first_d or today > cand.replace(day=7):
        cand = today.replace(year=y + 1, month=month, day=1)
    return cand


def irp_section(results: list) -> tuple[str, dict]:
    raw = os.environ.get("IRP_CONFIG")
    if not raw:
        return "", {}
    try:
        cfg = json.loads(raw.lstrip("\ufeff").strip())  # PowerShell이 붙이는 BOM 제거
        hold, w = cfg["holdings"], cfg["weights"]
        R, monthly = float(cfg["remaining"]), float(cfg.get("monthly", 750000))
        sig = {ix["key"]: int(r["buy_months"]) for ix, r, _ in results}
        keys = [ix["key"] for ix, _, _ in results if ix["key"] in KR_ETF]

        price, pdate = {}, ""
        for k in keys:
            price[k], pdate = _kr_price(KR_ETF[k][0])
        V = {k: hold.get(k, 0) * price[k] for k in keys}
        Vt = sum(V.values())

        # 남은 개월 / 이번 달 정기 매수 완료 여부 (남은 투자금으로 추정)
        def ym(x):
            y, m = map(int, x.split("-"))
            return y * 12 + m
        now = _today_kst()
        cur, st, en = now.year * 12 + now.month, ym(cfg["start"]), ym(cfg["end"])
        if cur < st:
            done, M = True, en - st + 1
        else:
            m_incl = max(0, en - cur + 1)
            done = R <= monthly * (m_incl - 1) + monthly * 0.1
            M = m_incl - 1 if done else m_incl
        pulled = max(0.0, monthly * M - R)

        # 계획 끝에 목표 비중이 되도록 남은 투자금을 나누기 (매도 없음)
        gap = {k: max(0.0, w[k] * (Vt + R) - V[k]) for k in keys}
        g = sum(gap.values()) or 1.0
        gap = {k: gap[k] * R / g for k in keys}
        base = {k: (gap[k] / M if M > 0 else 0.0) for k in keys}

        # 우선 매수 모드: 지정한 ETF가 목표 비중이 될 때까지 월 적립액을 그 ETF에 먼저
        prio, prio_line, rest = cfg.get("priority"), "", set()
        if prio in keys and M > 0:
            need = max(0.0, (w[prio] * Vt - V[prio]) / (1 - w[prio]))  # 신규 자금만으로 목표 비중까지
            if need > monthly * 0.05:
                bp = min(monthly, need)
                rest = monthly - bp
                others = [k for k in keys if k != prio]
                og = sum(gap[k] for k in others) or 1.0
                base = {k: (bp if k == prio else rest * gap[k] / og) for k in keys}
                gap[prio] = need
                rest = set(others)
                prio_line = (f"{KR_ETF[prio][1]} 우선: 비중 {100 * V[prio] / Vt:.0f}% → {100 * w[prio]:.0f}%까지 "
                             f"{_man(need)} (약 {need / monthly:.1f}개월), 그동안 나머지는 쉬기")

        lines = [f"💼 <b>내 IRP</b> ({pdate} 국내 종가)",
                 f"평가 {_man(Vt)} · 남은 투자금 {_man(R)} · 남은 {M}개월",
                 "비중 " + " / ".join(f"{100 * V[k] / Vt:.0f}" for k in keys) + "% → 목표 "
                 + " / ".join(f"{100 * w[k]:.0f}" for k in keys) + "%",
                 "이번 달 정기 매수: 완료 ✅ (아래는 다음 달 기준)" if done else "이번 달 정기 매수: <b>아직</b>"]
        if prio_line:
            lines.append(prio_line)
        for k in keys:
            sh = round(base[k] / price[k])
            line = f"• {KR_ETF[k][1]}: 기본 {sh}주 ({_man(base[k])}) · 신호 {sig.get(k, 0)}개월분"
            mk = sig.get(k, 0)
            if mk >= 2:
                amt = min(base[k] * mk, gap[k])
                line += f" → 하락 구간 최대 {round(amt / price[k])}주 ({_man(amt)})"
            lines.append(line)
        if pulled > monthly * 0.1:
            lines.append(f"앞당겨 쓴 금액: {_man(pulled)} (그만큼 이후 정기 매수 쉬기)")
        # ---- 리밸런싱 ----
        rebal = False
        rb = next_rebalance(now, cfg.get("rebalance_first", "2027-03"), int(cfg.get("rebalance_month", 1)))
        days = (rb - now).days
        rb_txt = f"{rb.year}년 {rb.month}월 첫째 주"
        if days <= 0 or 0 < days <= 7:
            rebal = days <= 0
            lines.append(("🔄 <b>리밸런싱 주간</b> (" if rebal else f"🔄 <b>다음 주 리밸런싱 예정</b> ({rb_txt}, ")
                         + "목표 비중 맞추기 · 매도 먼저, 그 돈으로 매수)")
            for k in keys:
                diff = w[k] * Vt - V[k]
                sh = int(round(diff / price[k]))
                if sh == 0:
                    lines.append(f"• {KR_ETF[k][1]}: 그대로")
                else:
                    lines.append(f"• {KR_ETF[k][1]}: {'+' if sh > 0 else ''}{sh}주 {'매수' if sh > 0 else '매도'} "
                                 f"({'+' if diff > 0 else ''}{_man(diff)})")
            lines.append("IRP 안 매도라 세금 없음 · 끝나면 update_irp.ps1 로 수량 업데이트")
        else:
            lines.append(f"다음 리밸런싱: {rb_txt} (D-{days})")
        limit = float(cfg.get("irp_total", 50000000)) * 0.7
        if Vt > limit * 0.95:
            lines.append(f"⚠ 위험자산 {_man(Vt)} / 한도 {_man(limit)} (70%)에 근접")
        lines.append("<i>매수 후 update_irp.ps1 로 보유 수량·남은 투자금 업데이트</i>")
        ctx = {"done": done, "rest": rest, "prio_name": KR_ETF[prio][1] if prio in KR_ETF else "", "rebal": rebal}
        return "\n".join(lines), ctx
    except Exception as e:  # noqa: BLE001
        return f"💼 내 IRP: 계산 실패 ({_html.escape(type(e).__name__)})", {}


def telegram_message(results: list) -> str:
    r0 = max((r for _, r, _ in results), key=lambda r: r["date"])
    head = (f"🧭 <b>투자온도계</b> {r0['date']} 종가\n"
            f"공탐 {_f(r0['fear_greed'])} · VIX {_f(r0['vix'])} (점수 ≥30/40/50)\n")
    if WARNINGS:
        head += "\n⚠ <b>확인 필요</b>\n" + "".join(f"• {_html.escape(w)}\n" for w in WARNINGS)
    else:
        head += f"✅ 데이터 확인: 모두 {r0['date']} 값\n"
    latest = max(r["date"] for _, r, _ in results)
    irp, ctx = irp_section(results)
    body = "\n\n".join(index_block(ix, r, full, latest, ctx) for ix, r, full in results)
    return head + "\n" + body + (f"\n\n{irp}" if irp else "")


def _post_telegram(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                        "disable_web_page_preview": True}, timeout=20).raise_for_status()


def send_failure_alert(e: Exception) -> None:
    msg = (f"⚠ <b>투자온도계 업데이트 실패</b>\n"
           f"원인: {_html.escape(type(e).__name__)}: {_html.escape(str(e))[:300]}\n\n"
           f"대시보드는 이전 값 그대로입니다.\n"
           f"GitHub → Actions → 투자온도계 업데이트 → Run workflow 로 다시 실행해 보세요.").replace("\n", "\n")
    try:
        _post_telegram(msg)
        (BASE / ".alert_sent").write_text("1")
        print(" 실패 알림 전송", file=sys.stderr)
    except Exception as e2:  # noqa: BLE001
        print(f"[경고] 실패 알림도 전송 실패: {type(e2).__name__}", file=sys.stderr)


def send_telegram(results: list) -> None:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return  # 설정 안 돼 있으면 조용히 건너뜀 (PC 실행 등)
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": telegram_message(results), "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=20,
        )
        resp.raise_for_status()
        print(" 텔레그램 전송 완료")
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 텔레그램 전송 실패: {type(e).__name__}", file=sys.stderr)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 작업 스케줄러 실행 시 인코딩 오류 방지
    except Exception:  # noqa: BLE001
        pass
    try:
        run()
    except Exception as e:  # noqa: BLE001
        send_failure_alert(e)
        raise


def run() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="이 날짜부터 다시 채우기 (YYYY-MM-DD)")
    ap.add_argument("--only", help="이 지수만 (ndx/spx/sox)")
    args = ap.parse_args()

    targets = [ix for ix in INDEXES if not args.only or ix["key"] == args.only]
    fulls = {ix["key"]: (pd.read_csv(BASE / ix["full"]) if (BASE / ix["full"]).exists() else pd.DataFrame())
             for ix in INDEXES}
    starts = {}
    for ix in targets:
        f = fulls[ix["key"]]
        starts[ix["key"]] = (pd.Timestamp(args.since) if args.since
                             else pd.Timestamp(f["date"].max()) if not f.empty
                             else pd.Timestamp(BACKFILL_START))

    since = (min(starts.values()) - pd.Timedelta(days=7)).date().isoformat()
    fg_cnn = fetch_fear_greed(since)
    fg_src = {d: "cnn" for d in fg_cnn}
    fg = dict(fg_cnn)
    vix = fetch_vix()

    # 지수 가격 (지수 하나가 실패해도 나머지는 계속)
    dfs = {}
    for ix in targets:
        try:
            dfs[ix["key"]] = fetch_index(ix["ticker"])
        except Exception as e:  # noqa: BLE001
            WARNINGS.append(f"{ix['tab']} 가격 수집 실패 → 이전 값 표시 ({type(e).__name__})")
    if targets and not dfs:
        raise RuntimeError("세 지수 가격을 모두 가져오지 못했습니다 (야후 파이낸스)")
    expected = max(df.index[-1] for df in dfs.values()).date().isoformat() if dfs else None

    # 공포탐욕: 오늘 값이 CNN에 없으면 대체 출처
    if expected and expected not in fg:
        bk = fetch_fear_greed_backup()
        for d, v in bk.items():
            if d not in fg:
                fg[d], fg_src[d] = v, "backup"
    # 저장해 둔 과거 값으로 빈 날 채우기 (모든 지수 기록에서)
    for f in fulls.values():
        if not f.empty:
            for _, r in f.dropna(subset=["fear_greed"]).iterrows():
                if r["date"] not in fg:
                    fg[r["date"]], fg_src[r["date"]] = (float(r["fear_greed"]), r["fear_greed_rating"]), "stored"

    # ---- 오늘 값 확인 ----
    if expected:
        src = fg_src.get(expected)
        if src is None:
            WARNINGS.append(f"공탐: {expected} 값 수집 실패 → 점수·★ 계산에서 빠짐")
        elif src == "backup":
            WARNINGS.append("공탐: CNN 수집 실패 → 대체 출처(GitHub 공개 데이터) 값 사용")
        if vix.empty:
            WARNINGS.append("VIX: 수집 실패 → 점수에서 빠짐")
        elif vix.index[-1].date().isoformat() < expected:
            WARNINGS.append(f"VIX: {vix.index[-1].date().isoformat()} 값 사용 (최신 아님)")
        should = latest_us_trading_day()
        if expected < should:
            WARNINGS.append(f"가격: 최신 거래일({should}) 데이터가 아직 없음 → {expected} 값 (미국 휴장일이면 정상)")

    results = []
    for ix in INDEXES:
        full = fulls[ix["key"]]
        if ix["key"] in dfs:
            df = dfs[ix["key"]]
            dates = [d for d in df.index if d >= starts[ix["key"]]]
            new = pd.DataFrame(build_rows(df, dates, fg, vix))
            if not full.empty:
                full = full[~full["date"].isin(new["date"])]
            full = pd.concat([full, new], ignore_index=True).sort_values("date").reset_index(drop=True)
            full.to_csv(BASE / ix["full"], index=False, encoding="utf-8-sig")
            print(f" [{ix['name']}] 계산 {len(new)}일 / 원본 {len(full)}일")
        if full.empty:
            continue
        hist = compact(full)
        hist.to_csv(BASE / ix["hist"], index=False, encoding="utf-8-sig")
        render_page(ix, hist, monthly_best(full), full)
        results.append((ix, full.iloc[-1], full))
        if expected and full["date"].max() < expected and not any(w.startswith(ix["tab"]) for w in WARNINGS):
            WARNINGS.append(f"{ix['tab']}: {full['date'].max()} 값 (최신 {expected} 아님)")

    for ix, row, _ in results:
        print(f"\n===== {ix['name']}  {row['date']} =====")
        print(f" 종가 {row['nas100_close']:,.2f} ({row['drawdown_pct']:+.2f}%) · 전고점 {row['ath_close']:,.2f} ({row['ath_date']})")
        print(f" RSI 일 {row['rsi_daily']} / 주 {row['rsi_weekly']} · Slow {row['slow_k']} · 공탐 {row['fear_greed']} · VIX {row['vix']}")
        print(f" 📐 매수 점수 {int(row['buy_score'])}점 ({row['buy_zone']}) → 추가 매수 {int(row['buy_months'])}개월분"
              f" · 이평선 {row['ma_level'] or '-'}")
    print("\n 확인: " + (" / ".join(WARNINGS) if WARNINGS else "모두 최신 값"))
    print(f"\n 페이지: {SITE}\n")
    send_telegram(results)


if __name__ == "__main__":
    main()

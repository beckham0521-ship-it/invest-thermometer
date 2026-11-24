"""투자온도계 웹: 대시보드(site/) + 매매 기록 페이지·API.
Tailscale serve(tailnet 전용) 뒤에서 127.0.0.1:8768 로만 열림.

실행: python webapp.py            (PC 시험: http://127.0.0.1:8768)
환경변수: THERMO_DATA = 매매 기록·가격 파일 폴더, THERMO_PORT (기본 8768)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

import trades as T

BASE = Path(__file__).resolve().parent
SITE = BASE / "site"
app = Flask(__name__, static_folder=None)


def _plan_total() -> float:
    f = T.data_dir() / "irp.json"
    try:
        return float(json.loads(f.read_text(encoding="utf-8-sig")).get("plan_total", 30_000_000))
    except Exception:  # noqa: BLE001
        return 30_000_000.0


def _guard():
    # 다른 사이트에서 몰래 보내는 요청(CSRF) 막기: 이 페이지 스크립트만 붙이는 헤더 확인
    if request.headers.get("X-Thermo") != "1":
        abort(403)


@app.after_request
def _headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/") or request.path == "/trades":
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- 대시보드 ----------
@app.get("/")
def index():
    return send_from_directory(SITE, "index.html")


@app.get("/<name>.html")
def page(name):
    if name not in ("index", "sox", "spx"):
        abort(404)
    return send_from_directory(SITE, f"{name}.html")


@app.get("/trades")
def trades_page():
    return send_from_directory(BASE, "trades.html")


# ---------- API ----------
@app.get("/api/trades")
def api_list():
    prices, pdate = T.load_prices()
    rows = T.load()
    return jsonify(trades=rows, summary=T.summary(rows, prices, _plan_total()), price_date=pdate,
                   etfs={k: v[1] for k, v in T.ETFS.items()}, kinds=T.KINDS)


@app.post("/api/trades")
def api_add():
    _guard()
    try:
        return jsonify(ok=True, trade=T.add(request.get_json(force=True) or {}))
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400


@app.put("/api/trades/<int:tid>")
def api_update(tid):
    _guard()
    try:
        return jsonify(ok=True, trade=T.update(tid, request.get_json(force=True) or {}))
    except KeyError:
        abort(404)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400


@app.delete("/api/trades/<int:tid>")
def api_delete(tid):
    _guard()
    try:
        T.delete(tid)
        return jsonify(ok=True)
    except KeyError:
        abort(404)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400


if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("THERMO_PORT", "8768"))
    print(f"투자온도계 웹: http://127.0.0.1:{port}  (데이터: {T.data_dir()})")
    serve(app, host="127.0.0.1", port=port, threads=4)

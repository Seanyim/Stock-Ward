# engine/technical.py — live price + technical analysis (no API key).
#
# Pulls daily closes from Yahoo's public chart endpoint, computes standard
# indicators on the NEWEST data, and derives a 0–100 technical score plus a
# bilingual read. Also exposes a live quote (latest price + as-of time).
import math
from datetime import datetime, timezone

import requests

_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{t}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Stock-Ward/4"}


def _fetch_chart(ticker, rng="2y", interval="1d", proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(_CHART.format(t=ticker), params={"range": rng, "interval": interval},
                     headers=_HEADERS, timeout=12, proxies=proxies)
    r.raise_for_status()
    res = (r.json().get("chart") or {}).get("result") or []
    if not res:
        return None
    res = res[0]
    meta = res.get("meta") or {}
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes, dates = [], []
    for i, t in enumerate(ts):
        c = (q.get("close") or [None] * len(ts))[i]
        if c is not None:
            closes.append(float(c))
            dates.append(datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"))
    return {"meta": meta, "dates": dates, "closes": closes}


# ---- indicator helpers (pure python) ----
def _sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None


def _ema_series(v, n):
    if len(v) < n:
        return []
    k = 2 / (n + 1)
    e = sum(v[:n]) / n
    out = [e]
    for x in v[n:]:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def _rsi(v, n=14):
    if len(v) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = v[i] - v[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def _macd(v):
    e12, e26 = _ema_series(v, 12), _ema_series(v, 26)
    if not e12 or not e26:
        return None, None, None
    n = min(len(e12), len(e26))
    macd_line = [e12[-n + i] - e26[-n + i] for i in range(n)]
    sig = _ema_series(macd_line, 9)
    if not sig:
        return macd_line[-1], None, None
    return macd_line[-1], sig[-1], macd_line[-1] - sig[-1]


def _ret(v, days):
    if len(v) > days and v[-days - 1]:
        return (v[-1] / v[-days - 1] - 1) * 100
    return None


def live_quote(ticker, proxy=None):
    try:
        ch = _fetch_chart(ticker, rng="5d", interval="1d", proxy=proxy)
        m = ch["meta"] if ch else {}
        price = m.get("regularMarketPrice")
        prev = m.get("chartPreviousClose") or m.get("previousClose")
        t = m.get("regularMarketTime")
        asof = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if t else None
        chg = (price - prev) if (price is not None and prev) else None
        return {"price": price, "prev_close": prev, "as_of": asof,
                "change": chg, "change_pct": (chg / prev * 100) if (chg is not None and prev) else None,
                "currency": m.get("currency"), "exchange": m.get("fullExchangeName")}
    except Exception as e:
        return {"error": str(e)}


def analyze(ticker, proxy=None):
    """Technical indicators + 0–100 score + bilingual read, on the newest price."""
    ch = _fetch_chart(ticker, rng="2y", interval="1d", proxy=proxy)
    if not ch or len(ch["closes"]) < 30:
        return {"error": "insufficient_price_data"}
    v = ch["closes"]
    meta = ch["meta"]
    price = meta.get("regularMarketPrice") or v[-1]
    t = meta.get("regularMarketTime")
    asof = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if t else ch["dates"][-1]

    sma20, sma50, sma200 = _sma(v, 20), _sma(v, 50), _sma(v, 200)
    rsi = _rsi(v, 14)
    macd, macd_sig, macd_hist = _macd(v)
    win = v[-252:] if len(v) >= 252 else v
    hi52, lo52 = max(win), min(win)
    pos52 = (price - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else None
    rets = {"1m": _ret(v, 21), "3m": _ret(v, 63), "6m": _ret(v, 126), "1y": _ret(v, 252)}
    # annualized volatility
    rel = [v[i] / v[i - 1] - 1 for i in range(1, len(v))][-252:]
    vol = (sum((x - sum(rel) / len(rel)) ** 2 for x in rel) / len(rel)) ** 0.5 * math.sqrt(252) * 100 if rel else None

    # ---- composite technical score 0–100 ----
    pts, w = 0.0, 0.0
    def add(cond_score, weight):
        nonlocal pts, w
        pts += cond_score * weight
        w += weight
    if sma50:  add(100 if price > sma50 else 25, 1.0)
    if sma200: add(100 if price > sma200 else 20, 1.2)
    if sma50 and sma200: add(100 if sma50 > sma200 else 25, 1.0)   # golden/death cross
    if rsi is not None:
        add(85 if 50 <= rsi <= 70 else 60 if 40 <= rsi < 50 else 40 if rsi > 70 else 30, 0.8)
    if macd_hist is not None: add(100 if macd_hist > 0 else 30, 0.8)
    if pos52 is not None: add(pos52, 1.0)            # higher in 52w range = stronger
    if rets["3m"] is not None: add(max(0, min(100, 50 + rets["3m"] * 2)), 0.8)
    score = round(pts / w, 1) if w else None

    if score is None: trend_en, trend_zh = "n/a", "暂无"
    elif score >= 70: trend_en, trend_zh = "bullish / uptrend", "偏多 / 上升趋势"
    elif score >= 45: trend_en, trend_zh = "neutral / consolidating", "中性 / 盘整"
    else: trend_en, trend_zh = "bearish / downtrend", "偏空 / 下降趋势"

    def f(x, d=2): return round(x, d) if isinstance(x, (int, float)) else None
    return {
        "as_of": asof, "price": f(price), "score": score,
        "trend_en": trend_en, "trend_zh": trend_zh,
        "sma20": f(sma20), "sma50": f(sma50), "sma200": f(sma200),
        "rsi14": f(rsi, 1), "macd": f(macd, 3), "macd_signal": f(macd_sig, 3), "macd_hist": f(macd_hist, 3),
        "hi52": f(hi52), "lo52": f(lo52), "pos52_pct": f(pos52, 1),
        "ret_1m": f(rets["1m"], 1), "ret_3m": f(rets["3m"], 1), "ret_6m": f(rets["6m"], 1), "ret_1y": f(rets["1y"], 1),
        "volatility_pct": f(vol, 1),
        "series": {"dates": ch["dates"][-260:], "close": [f(x) for x in v[-260:]]},
    }

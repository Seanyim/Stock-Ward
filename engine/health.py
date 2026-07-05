# engine/health.py — live connectivity status for every data source.
#
# Returns one entry per source with a status:
#   "live"  — reachable now (green)
#   "nokey" — works but needs an API key the user hasn't provided (amber)
#   "down"  — unreachable / error right now (red)
# Pings run concurrently with a short timeout so the UI stays snappy.
from concurrent.futures import ThreadPoolExecutor

import requests

from engine.providers.common import get_key

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Stock-Ward/4"}
_TIMEOUT = 4

# name, kind, probe-url, requires-key
_PROBES = [
    ("yfinance",   "financials+price+news", "https://query1.finance.yahoo.com/v8/finance/chart/AAPL", None),
    ("sec_edgar",  "official financials",   "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/Assets.json", None),
    ("nasdaq",     "financials+analyst",    "https://api.nasdaq.com/api/company/AAPL/financials?frequency=1", None),
    ("stooq",      "price history",         "https://stooq.com/q/d/l/?s=aapl.us&i=d", None),
    ("stocktwits", "social discussion",     "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json", None),
]


def _ping(name, kind, url, key_name):
    if key_name:
        key = get_key(key_name)
        if not key:
            return {"name": name, "kind": kind, "status": "nokey"}
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}apikey={key}"
    try:
        # SEC requires a descriptive UA; others are fine with it too.
        headers = dict(_UA)
        if name == "sec_edgar":
            headers["User-Agent"] = get_key("SEC_USER_AGENT") or "Stock-Ward research stockward@example.com"
        r = requests.get(url, headers=headers, timeout=_TIMEOUT, stream=True)
        # Yahoo sometimes returns 429 when rate-limited but is still "reachable".
        ok = r.status_code < 500 and r.status_code not in (401, 403)
        r.close()
        return {"name": name, "kind": kind, "status": "live" if ok else "down"}
    except Exception:
        return {"name": name, "kind": kind, "status": "down"}


def connection_status():
    """Concurrent live status for all sources. Order preserved."""
    with ThreadPoolExecutor(max_workers=len(_PROBES)) as ex:
        results = list(ex.map(lambda p: _ping(*p), _PROBES))
    return results

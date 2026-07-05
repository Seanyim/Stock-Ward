# engine/news.py — ticker news fetch + lightweight pros / cons / forward analysis.
#
# Source: yfinance .news (no API key). Each headline is sentiment-tagged with a
# finance lexicon and bucketed into pros (bullish), cons (bearish), and
# forward-looking effects. A readable summary is synthesized from the buckets.
from datetime import datetime

from engine import db

POS_WORDS = {
    "beat", "beats", "surge", "surges", "soar", "soars", "rally", "rallies",
    "record", "growth", "grows", "upgrade", "upgraded", "outperform", "raise",
    "raises", "raised", "strong", "gains", "gain", "jumps", "jump", "profit",
    "profits", "boost", "boosts", "wins", "win", "approval", "approved",
    "expansion", "expand", "buyback", "dividend", "bullish", "tops", "top",
    "high", "highs", "breakthrough", "partnership", "demand",
}
NEG_WORDS = {
    "miss", "misses", "missed", "plunge", "plunges", "drop", "drops", "fall",
    "falls", "slump", "downgrade", "downgraded", "underperform", "cut", "cuts",
    "weak", "loss", "losses", "decline", "declines", "lawsuit", "probe",
    "investigation", "recall", "warning", "warns", "warn", "layoff", "layoffs",
    "bearish", "fraud", "delay", "delays", "halt", "concern", "concerns",
    "risk", "risks", "slowdown", "selloff", "low", "lows", "fine", "penalty",
}
FORWARD_WORDS = {
    "guidance", "forecast", "forecasts", "outlook", "expects", "expected",
    "will", "plans", "plan", "to launch", "upcoming", "next quarter", "target",
    "targets", "projection", "projected", "anticipates", "roadmap", "future",
    "2026", "2027", "long-term", "estimate", "estimates",
}


def _sentiment(text):
    t = (text or "").lower()
    pos = sum(1 for w in POS_WORDS if w in t)
    neg = sum(1 for w in NEG_WORDS if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _normalize_item(raw):
    """Handle both legacy flat and new nested yfinance news schemas."""
    if "content" in raw and isinstance(raw["content"], dict):
        c = raw["content"]
        prov = (c.get("provider") or {}).get("displayName")
        url = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url")
        return {
            "uuid": raw.get("id") or c.get("id") or url or c.get("title"),
            "title": c.get("title"),
            "publisher": prov,
            "link": url,
            "published": c.get("pubDate") or c.get("displayTime"),
            "summary": c.get("summary") or c.get("description"),
        }
    ts = raw.get("providerPublishTime")
    pub = (datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
           if isinstance(ts, (int, float)) else raw.get("published"))
    return {
        "uuid": raw.get("uuid") or raw.get("link"),
        "title": raw.get("title"),
        "publisher": raw.get("publisher"),
        "link": raw.get("link"),
        "published": pub,
        "summary": raw.get("summary"),
    }


def fetch_news(ticker, proxy=None, limit=40):
    """Fetch, sentiment-tag, and store recent news for a ticker."""
    import os
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
    items, err = [], None
    try:
        import yfinance as yf
        raw_list = yf.Ticker(ticker).news or []
        for raw in raw_list[:limit]:
            it = _normalize_item(raw)
            if not it.get("title"):
                continue
            it["sentiment"] = _sentiment(f"{it.get('title','')} {it.get('summary','')}")
            items.append(it)
    except Exception as e:
        err = str(e)
    if items:
        db.save_news(ticker, items)
    return {"ok": bool(items), "count": len(items), "error": err}


_REDDIT_SUBS = "wallstreetbets+stocks+investing+StockMarket+options+ValueInvesting+Daytrading"


def _fetch_reddit(ticker, limit=40):
    """Reddit discussion (keyless). Real engagement = upvotes + comments.
    Searches the major finance subreddits for the ticker and the $cashtag."""
    import requests
    from datetime import datetime, timezone
    headers = {"User-Agent": "StockWard/4 (finance research; contact: user)"}
    out, seen = [], set()
    queries = [
        (f"https://www.reddit.com/r/{_REDDIT_SUBS}/search.json",
         {"q": ticker, "restrict_sr": 1, "sort": "top", "t": "month", "limit": 40}),
        (f"https://www.reddit.com/r/{_REDDIT_SUBS}/search.json",
         {"q": ticker, "restrict_sr": 1, "sort": "top", "t": "year", "limit": 40}),
        ("https://www.reddit.com/search.json",
         {"q": f"${ticker}", "sort": "top", "t": "year", "limit": 25}),
    ]
    for url, params in queries:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            for ch in (r.json().get("data") or {}).get("children", []):
                d = ch.get("data") or {}
                pid = d.get("id")
                if not pid or pid in seen or not d.get("title"):
                    continue
                seen.add(pid)
                score = int(d.get("score") or 0)
                ncom = int(d.get("num_comments") or 0)
                text = f"{d.get('title','')} {d.get('selftext','')}"
                created = d.get("created_utc")
                out.append({
                    "msg_id": pid,
                    "title": d.get("title"),
                    "body": (d.get("selftext") or "")[:280],
                    "user": "r/" + (d.get("subreddit") or ""),
                    "name": d.get("author"),
                    "platform": "reddit",
                    "engagement": score + ncom * 2,
                    "followers": score,            # reuse: upvotes as the "reach" proxy
                    "comments": ncom,
                    "official": score >= 200,      # high-traction post
                    "created": (datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")
                                if created else None),
                    "sentiment": _sentiment(text),
                    "link": "https://www.reddit.com" + (d.get("permalink") or ""),
                })
        except Exception:
            continue
    out.sort(key=lambda m: m["engagement"], reverse=True)
    return out[:limit]


def _fetch_stocktwits(ticker, limit=40):
    """Fallback only — used if Reddit is unavailable."""
    import requests
    out = []
    try:
        r = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json",
                         headers={"User-Agent": "Mozilla/5.0 Stock-Ward/4"}, timeout=12)
        r.raise_for_status()
        for m in (r.json().get("messages") or [])[:limit]:
            ent = (m.get("entities") or {}).get("sentiment") or {}
            basic = (ent.get("basic") or "").lower()
            sent = "positive" if basic == "bullish" else "negative" if basic == "bearish" else _sentiment(m.get("body", ""))
            u = m.get("user") or {}
            out.append({"msg_id": m.get("id"), "body": m.get("body"), "user": u.get("username"),
                        "name": u.get("name"), "platform": "stocktwits",
                        "engagement": int(u.get("followers") or 0), "followers": u.get("followers") or 0,
                        "official": bool(u.get("official")), "created": (m.get("created_at") or "")[:10],
                        "sentiment": sent,
                        "link": (m.get("entities") or {}).get("permalink") or f"https://stocktwits.com/symbol/{ticker}"})
    except Exception:
        pass
    return out


def fetch_social(ticker, proxy=None, limit=40):
    """Retail discussion from Reddit only (keyless, real engagement = upvotes +
    comments). StockTwits is no longer used. X/Twitter has no reliable keyless
    API, so it is not included."""
    items = _fetch_reddit(ticker, limit=limit)
    db.clear_social(ticker)
    if items:
        db.save_social(ticker, items)
    return {"ok": bool(items), "count": len(items), "platform": "reddit"}


def _social_digest(ticker, limit=80):
    """Summarize retail discussion ranked by REAL engagement (upvotes/comments),
    with an engagement-weighted tone and a readable bilingual summary."""
    msgs = db.get_social(ticker, limit=limit)
    if not msgs:
        return None
    platform = msgs[0].get("platform") or "reddit"
    pos = sum(1 for m in msgs if m.get("sentiment") == "positive")
    neg = sum(1 for m in msgs if m.get("sentiment") == "negative")
    neu = len(msgs) - pos - neg
    score = (pos - neg) / max(len(msgs), 1)
    tone = "bullish-leaning" if score > 0.15 else "bearish-leaning" if score < -0.15 else "mixed"
    tone_zh = "偏多" if score > 0.15 else "偏空" if score < -0.15 else "多空均衡"

    eng = lambda m: int(m.get("engagement") or 0)
    by_eng = sorted(msgs, key=eng, reverse=True)
    top = by_eng[:8]

    # engagement-weighted tone (a 500-upvote post counts far more than a 2-upvote one)
    wpos = sum(eng(m) + 1 for m in msgs if m.get("sentiment") == "positive")
    wneg = sum(eng(m) + 1 for m in msgs if m.get("sentiment") == "negative")
    wscore = (wpos - wneg) / max(wpos + wneg, 1)
    inf_tone = "bullish" if wscore > 0.15 else "bearish" if wscore < -0.15 else "mixed"
    inf_tone_zh = "偏多" if wscore > 0.15 else "偏空" if wscore < -0.15 else "中性"

    total_up = sum(eng(m) for m in msgs)
    src_label = "Reddit" if platform == "reddit" else "StockTwits"
    top_titles = "; ".join((m.get("title") or m.get("body") or "")[:60] for m in top[:3])
    summary_en = (f"{len(msgs)} {src_label} posts (total engagement ~{total_up:,}). "
                  f"By raw count the tone is {tone}; weighting by upvotes/comments it is {inf_tone}. "
                  f"Most-discussed threads: {top_titles}.")
    summary_zh = (f"{len(msgs)} 条 {src_label} 讨论（总热度约 {total_up:,}）。"
                  f"按条数情绪{tone_zh}；按点赞/评论加权则{inf_tone_zh}。"
                  f"热度最高话题：{top_titles}。")

    return {"count": len(msgs), "pos": pos, "neg": neg, "neu": neu, "platform": platform,
            "src_label": src_label,
            "score": round(score, 3), "tone": tone, "tone_zh": tone_zh,
            "influential": top, "influential_count": len(top),
            "inf_tone": inf_tone, "inf_tone_zh": inf_tone_zh, "inf_score": round(wscore, 3),
            "total_engagement": total_up,
            "summary_en": summary_en, "summary_zh": summary_zh,
            "messages": by_eng[:24]}


def analyze(ticker, limit=40):
    """Build pros / cons / forward buckets + a synthesized summary from stored news."""
    news = db.get_news(ticker, limit=limit)
    pros, cons, forward = [], [], []
    pos = neg = neu = 0
    for n in news:
        title = n.get("title") or ""
        text = f"{title} {n.get('summary') or ''}".lower()
        s = n.get("sentiment") or _sentiment(text)
        entry = {"title": title, "publisher": n.get("publisher"),
                 "link": n.get("link"), "published": n.get("published")}
        if s == "positive":
            pos += 1
            pros.append(entry)
        elif s == "negative":
            neg += 1
            cons.append(entry)
        else:
            neu += 1
        if any(w in text for w in FORWARD_WORDS):
            forward.append(entry)

    total = max(pos + neg + neu, 1)
    score = (pos - neg) / total
    if score > 0.15:
        tone = "net positive"
    elif score < -0.15:
        tone = "net negative"
    else:
        tone = "mixed / neutral"
    tone_zh = {"net positive": "偏多", "net negative": "偏空", "mixed / neutral": "中性偏均衡"}[tone]

    # --- English narrative -------------------------------------------------
    s = (f"Across {len(news)} recent headlines for {ticker}, coverage skews {tone} "
         f"({pos} bullish, {neg} bearish, {neu} neutral; sentiment score {score:+.2f}). ")
    if pros:
        s += "On the positive side, the dominant themes are: " + \
             "; ".join(p["title"] for p in pros[:3]) + ". "
    if cons:
        s += "The main concerns raised are: " + \
             "; ".join(c["title"] for c in cons[:3]) + ". "
    if forward:
        s += (f"{len(forward)} item(s) carry forward-looking signals (guidance, outlook or targets), "
              f"notably: {forward[0]['title']}. ")
    s += ("Net read: the flow leans constructive — watch for follow-through on the positive catalysts."
          if score > 0.15 else
          "Net read: sentiment is under pressure — weigh the flagged risks before adding."
          if score < -0.15 else
          "Net read: the balance of news is mixed; no clear directional bias from headlines alone.")

    social = _social_digest(ticker)
    if social:
        s += (f" Retail discussion ({social['src_label']}, {social['count']} posts) is {social['tone']} "
              f"({social['pos']} bullish / {social['neg']} bearish).")
        if social.get("influential"):
            names = ", ".join(f"“{(m.get('title') or m.get('body') or '')[:48]}” ({social['src_label']=='Reddit' and str(m.get('followers') or 0)+'↑' or ''})"
                              for m in social["influential"][:2])
            s += (f" Weighting by upvotes/comments the tone is {social['inf_tone']}; "
                  f"top threads: {names}.")

    # --- Chinese narrative -------------------------------------------------
    z = (f"近期 {len(news)} 条 {ticker} 相关新闻整体情绪{tone_zh}"
         f"（利多 {pos} 条、利空 {neg} 条、中性 {neu} 条，情绪分 {score:+.2f}）。")
    if pros:
        z += "正面主要集中在：" + "；".join(p["title"] for p in pros[:3]) + "。"
    if cons:
        z += "主要担忧包括：" + "；".join(c["title"] for c in cons[:3]) + "。"
    if forward:
        z += f"另有 {len(forward)} 条涉及前瞻信号（指引/展望/目标），重点：{forward[0]['title']}。"
    z += ("综合判断：新闻面偏积极，关注正面催化的持续性。" if score > 0.15 else
          "综合判断：情绪承压，加仓前需权衡上述风险。" if score < -0.15 else
          "综合判断：消息面多空交织，单凭新闻难定方向。")
    if social:
        z += (f" 散户讨论（{social['src_label']}，{social['count']} 条）整体{social['tone_zh']}"
              f"（看多 {social['pos']} / 看空 {social['neg']}）。")
        if social.get("influential"):
            names = "、".join(f"“{(m.get('title') or m.get('body') or '')[:32]}”"
                             for m in social["influential"][:2])
            z += f" 按点赞/评论热度加权整体{social['inf_tone_zh']}；最热话题：{names}。"

    return {
        "ticker": ticker, "count": len(news),
        "sentiment_score": round(score, 3), "tone": tone, "tone_zh": tone_zh,
        "counts": {"positive": pos, "negative": neg, "neutral": neu},
        "pros": pros[:12], "cons": cons[:12], "forward": forward[:12],
        "summary": s, "summary_zh": z,
        "social": social,
        "news": news[:limit],
    }

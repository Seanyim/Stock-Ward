# engine/grade.py — composite ticker grade + bilingual advice + narratives.
#
# Pure scoring/text layer. The server assembles the component inputs (from the
# valuation dashboard, master scores, QG-Pro, news sentiment and financial
# health) and passes them here; nothing in this module touches the DB.
import numpy as np

from engine.valuation import safe, _f


def _lin(x, lo, hi, out_lo=0.0, out_hi=100.0):
    if x is None:
        return None
    if hi == lo:
        return out_lo
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return out_lo + t * (out_hi - out_lo)


def financial_health(ctx):
    """0–100 from profitability, cash generation and leverage of latest TTM."""
    latest = ctx.get("latest")
    if latest is None:
        return None, {}
    roe = safe(latest, "ROE", None)
    npm = safe(latest, "NetProfitMargin", None)
    fcf_rev = safe(latest, "FCFToRevenue", None)
    # leverage: total liabilities / equity
    tl = safe(latest, "TotalLiabilities", None)
    eq = safe(latest, "TotalEquity", None)
    de = (tl / eq) if (tl and eq and eq > 0) else None

    parts, factors = [], {}
    if roe is not None:
        s = _lin(roe, 0, 30); parts.append((s, 0.30)); factors["ROE"] = _f(roe, 1)
    if npm is not None:
        s = _lin(npm, 0, 25); parts.append((s, 0.25)); factors["NetMargin"] = _f(npm, 1)
    if fcf_rev is not None:
        s = _lin(fcf_rev, 0, 25); parts.append((s, 0.25)); factors["FCF/Rev"] = _f(fcf_rev, 1)
    if de is not None:
        s = _lin(de, 3.0, 0.3); parts.append((s, 0.20)); factors["Debt/Equity"] = _f(de, 2)
    if not parts:
        return None, factors
    tw = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / tw
    return _f(score, 1), factors


WEIGHTS = {"valuation": 0.24, "growth": 0.14, "financial": 0.18, "masters": 0.18,
           "quality": 0.10, "technical": 0.10, "news": 0.06}


def growth_score(growth_rows):
    """0–100 from revenue / net-income / FCF CAGR (quarterly TTM-based)."""
    if not growth_rows:
        return None
    import numpy as np
    keys = {"Revenue", "NetIncome", "EPS", "FCF"}
    vals = [r["cagr_pct"] for r in growth_rows
            if r.get("metric") in keys and r.get("cagr_pct") is not None]
    if not vals:
        vals = [r["cagr_pct"] for r in growth_rows if r.get("cagr_pct") is not None]
    if not vals:
        return None
    g = float(np.median(vals))
    return _lin(g, -10, 30)   # -10% -> 0, +30% -> 100


def _letter(score):
    bands = [(87, "A+"), (83, "A"), (80, "A-"), (77, "B+"), (73, "B"), (70, "B-"),
             (67, "C+"), (63, "C"), (60, "C-"), (55, "D+"), (50, "D"), (0, "F")]
    for cut, g in bands:
        if score >= cut:
            return g
    return "F"


def compute_grade(margin_pct, confidence, masters_avg, qg_score, news_score, fin_health,
                  growth_score=None, technical_score=None):
    comp = {}
    comp["valuation"] = _lin(margin_pct, -30, 30) if margin_pct is not None else None
    comp["growth"] = growth_score
    comp["financial"] = fin_health
    comp["masters"] = masters_avg
    comp["quality"] = qg_score
    comp["technical"] = technical_score
    comp["news"] = news_score

    parts = [(comp[k], WEIGHTS[k]) for k in WEIGHTS if comp.get(k) is not None]
    if not parts:
        return {"grade": "N/A", "score": None, "components": comp}
    tw = sum(w for _, w in parts)
    score = sum(v * w for v, w in parts) / tw
    return {"grade": _letter(score), "score": _f(score, 1),
            "components": {k: _f(v, 1) if v is not None else None for k, v in comp.items()}}


def advice(grade_info, margin_pct, news_tone, lang="en"):
    g = grade_info.get("grade", "N/A")
    score = grade_info.get("score")
    c = grade_info.get("components", {})
    val, mas, fin = c.get("valuation"), c.get("masters"), c.get("financial")

    def tier(s):
        if s is None:
            return "na"
        return "strong" if s >= 70 else "ok" if s >= 50 else "weak"

    if lang == "zh":
        verdict = ("显著低估，安全边际充足" if (margin_pct or 0) > 15 else
                   "估值合理" if -15 <= (margin_pct or 0) <= 15 else "估值偏高")
        head = f"综合评级 {g}（{score}/100）。{verdict}。"
        bits = []
        bits.append(f"估值面{'强' if tier(val)=='strong' else '中性' if tier(val)=='ok' else '偏弱'}"
                    f"（安全边际 {_f(margin_pct,1) if margin_pct is not None else '—'}%）。")
        bits.append(f"大师评分维度{'优秀' if tier(mas)=='strong' else '中等' if tier(mas)=='ok' else '偏弱'}。")
        bits.append(f"财务健康度{'稳健' if tier(fin)=='strong' else '尚可' if tier(fin)=='ok' else '需关注'}。")
        bits.append(f"近期新闻情绪：{ {'net positive':'偏多','net negative':'偏空'}.get(news_tone,'中性') }。")
        if g in ("A+", "A", "A-"):
            rec = "倾向：可重点关注/逢低布局（请结合自身风险偏好与仓位管理）。"
        elif g in ("B+", "B", "B-"):
            rec = "倾向：可纳入观察名单，等待更好价格或催化剂。"
        elif g in ("C+", "C", "C-"):
            rec = "倾向：中性，建议进一步核实数据与基本面后再决策。"
        else:
            rec = "倾向：谨慎，估值或基本面存在明显短板。"
        disclaimer = "（本评级为量化综合参考，非投资建议。）"
        return head + " ".join(bits) + rec + disclaimer

    verdict = ("clearly undervalued with a solid margin of safety" if (margin_pct or 0) > 15 else
               "fairly valued" if -15 <= (margin_pct or 0) <= 15 else "richly valued")
    head = f"Composite grade {g} ({score}/100). The stock looks {verdict}. "
    bits = [
        f"Valuation is {tier(val)} (margin of safety { _f(margin_pct,1) if margin_pct is not None else '—'}%). ",
        f"Investor-lens scores are {tier(mas)}. ",
        f"Financial health is {tier(fin)}. ",
        f"Recent news sentiment is {news_tone or 'neutral'}. ",
    ]
    if g in ("A+", "A", "A-"):
        rec = "Bias: a high-conviction candidate worth accumulating on weakness (size to your own risk tolerance)."
    elif g in ("B+", "B", "B-"):
        rec = "Bias: watch-list quality — wait for a better entry price or a catalyst."
    elif g in ("C+", "C", "C-"):
        rec = "Bias: neutral — verify the data and fundamentals further before acting."
    else:
        rec = "Bias: cautious — valuation and/or fundamentals show clear weak spots."
    disclaimer = " (Quantitative composite for reference only, not investment advice.)"
    return head + "".join(bits) + rec + disclaimer


# ------------------------------------------------------------------
# Financial-report narrative (Fundamentals tab)
# ------------------------------------------------------------------
def financial_summary(ctx, lang="en"):
    """Narrative over annual FY history: growth, margins, cash, balance sheet."""
    df = ctx.get("df_raw")
    if df is None or df.empty:
        return "" if lang == "en" else ""
    fy = df[df["period"] == "FY"].sort_values("year") if "period" in df.columns else df
    if fy.empty or len(fy) < 2:
        return ("Insufficient annual history for a narrative summary."
                if lang == "en" else "年度历史数据不足，无法生成文字总结。")

    import pandas as pd
    def series(col):
        return pd.to_numeric(fy[col], errors="coerce") if col in fy.columns else pd.Series(dtype=float)

    rev = series("TotalRevenue").dropna()
    ni = series("NetIncome").dropna()
    yrs = fy["year"].astype(int).tolist()

    def cagr(s):
        s = s.dropna()
        if len(s) >= 2 and s.iloc[0] > 0 and s.iloc[-1] > 0:
            n = len(s) - 1
            return (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
        return None

    rev_cagr = cagr(rev)
    ni_cagr = cagr(ni)
    last = fy.iloc[-1]
    gm = (safe(last, "GrossProfit", 0) / safe(last, "TotalRevenue", 1) * 100) if safe(last, "TotalRevenue", 0) else None
    nm = (safe(last, "NetIncome", 0) / safe(last, "TotalRevenue", 1) * 100) if safe(last, "TotalRevenue", 0) else None
    y0, y1 = yrs[0], yrs[-1]

    if lang == "zh":
        out = f"{y0}–{y1} 财年：营收"
        out += f"年复合增速 {rev_cagr*100:.1f}%；" if rev_cagr is not None else "增速数据有限；"
        out += f"净利润复合增速 {ni_cagr*100:.1f}%。" if ni_cagr is not None else "净利润趋势数据有限。"
        if gm is not None:
            out += f" 最新毛利率 {gm:.1f}%"
        if nm is not None:
            out += f"、净利率 {nm:.1f}%。"
        ocf = safe(last, "OperatingCashFlow", 0); fcf = safe(last, "FreeCashFlow", 0)
        if ocf:
            out += f" 经营现金流 {ocf:.1f}B"
            if fcf:
                out += f"，自由现金流 {fcf:.1f}B。"
            else:
                out += "。"
        return out

    out = f"FY{y0}–FY{y1}: revenue "
    out += f"compounded at {rev_cagr*100:.1f}%/yr; " if rev_cagr is not None else "growth data limited; "
    out += f"net income compounded at {ni_cagr*100:.1f}%/yr. " if ni_cagr is not None else "net-income trend limited. "
    if gm is not None:
        out += f"Latest gross margin {gm:.1f}%"
    if nm is not None:
        out += f", net margin {nm:.1f}%. "
    ocf = safe(last, "OperatingCashFlow", 0); fcf = safe(last, "FreeCashFlow", 0)
    if ocf:
        out += f"Operating cash flow {ocf:.1f}B"
        out += f", free cash flow {fcf:.1f}B." if fcf else "."
    return out

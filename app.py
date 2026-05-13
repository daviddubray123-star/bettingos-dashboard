"""BettingOS v2 Dashboard — Streamlit Cloud.

Pulls live data from 4 Notion DBs via direct HTTP and renders 8 tabs.
No notion-client dependency — just stdlib urllib + Notion REST API.

Secrets configured in Streamlit Cloud → Settings → Secrets.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="BettingOS Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
    PICKS_DB = st.secrets["PICKS_DB"]
    DAILY_DB = st.secrets["DAILY_DB"]
    STRAT_DB = st.secrets["STRAT_DB"]
    JOURNAL_DB = st.secrets["JOURNAL_DB"]
except KeyError as e:
    st.error(f"Missing secret: {e}. Configure in Streamlit Cloud → Settings → Secrets.")
    st.stop()

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


# ─────────────────────────────────────────────────────────────────
# Direct Notion HTTP helpers
# ─────────────────────────────────────────────────────────────────

def _notion_post(path: str, body: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        f"{NOTION_API}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def iterate_db(db_id: str, max_pages: int = 10) -> list:
    results = []
    cursor = None
    for _ in range(max_pages):
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        try:
            response = _notion_post(f"/databases/{db_id}/query", body)
        except urllib.error.HTTPError as e:
            st.error(f"Notion API {e.code} for DB {db_id[:8]}…: {e.reason}")
            return results
        except Exception as e:
            st.error(f"Notion fetch failed for DB {db_id[:8]}…: {type(e).__name__}: {e}")
            return results
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return results


def get_prop(row, name):
    prop = row.get("properties", {}).get(name)
    if not prop:
        return None
    t = prop.get("type")
    if t == "title":
        return "".join(x.get("plain_text", "") for x in prop.get("title", []))
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in prop.get("rich_text", []))
    if t == "number":
        return prop.get("number")
    if t == "select":
        return (prop.get("select") or {}).get("name")
    if t == "multi_select":
        return [s["name"] for s in prop.get("multi_select", [])]
    if t == "date":
        return (prop.get("date") or {}).get("start")
    if t == "checkbox":
        return prop.get("checkbox")
    if t == "url":
        return prop.get("url")
    if t == "formula":
        f = prop.get("formula", {})
        ft = f.get("type")
        return f.get(ft) if ft else None
    return None


# ─────────────────────────────────────────────────────────────────
# Data fetchers (15-min cache)
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=900)
def fetch_picks():
    rows = iterate_db(PICKS_DB)
    picks = []
    for r in rows:
        picks.append({
            "id": r["id"],
            "date": (get_prop(r, "Date") or "")[:10],
            "sport": get_prop(r, "Sport") or "",
            "pick": get_prop(r, "Pick") or "",
            "strategy": get_prop(r, "Strategy") or "",
            "tier": get_prop(r, "Tier") or "",
            "account": get_prop(r, "Account") or "",
            "stake": get_prop(r, "Stake $") or 0,
            "odds": get_prop(r, "Odds") or 0,
            "result": get_prop(r, "Result") or "Pending",
            "net": get_prop(r, "Net P/L $") or 0,
            "era": get_prop(r, "Era") or "",
        })
    return sorted(picks, key=lambda p: p["date"] or "0000", reverse=True)


@st.cache_data(ttl=900)
def fetch_daily():
    rows = iterate_db(DAILY_DB)
    daily = []
    for r in rows:
        title = get_prop(r, "Date") or ""
        date_str = title[:10] if title and title[:4].isdigit() else ""
        daily.append({
            "date": date_str,
            "title": title,
            "bankroll_start": get_prop(r, "Bankroll Start $") or 0,
            "bankroll_end": get_prop(r, "Bankroll End $") or 0,
            "net": get_prop(r, "Net P/L $") or 0,
            "live_w": get_prop(r, "Live W") or 0,
            "live_l": get_prop(r, "Live L") or 0,
            "live_picks": get_prop(r, "Live Picks") or 0,
            "live_roi": get_prop(r, "Live ROI %") or 0,
            "live_stake": get_prop(r, "Live Stake $") or 0,
            "paper_w": get_prop(r, "Paper W") or 0,
            "paper_l": get_prop(r, "Paper L") or 0,
            "paper_picks": get_prop(r, "Paper Picks") or 0,
            "paper_roi": get_prop(r, "Paper ROI %") or 0,
            "notes": get_prop(r, "Notes") or "",
            "day_type": get_prop(r, "Day Type") or "",
            "grade": get_prop(r, "Process Grade") or "",
        })
    return sorted([d for d in daily if d["date"]], key=lambda d: d["date"])


@st.cache_data(ttl=900)
def fetch_strategies():
    rows = iterate_db(STRAT_DB)
    strats = []
    for r in rows:
        strats.append({
            "name": get_prop(r, "Strategy") or "",
            "sport": get_prop(r, "Sport") or "",
            "status": get_prop(r, "Status") or "",
            "picks": get_prop(r, "Picks (n)") or get_prop(r, "Picks") or 0,
            "won": get_prop(r, "Won") or 0,
            "lost": get_prop(r, "Lost") or 0,
            "hit_rate": get_prop(r, "Hit Rate %") or 0,
            "net": get_prop(r, "Net P/L $") or 0,
            "roi": get_prop(r, "ROI %") or 0,
            "last_fired": get_prop(r, "Last Fired") or "",
        })
    return strats


@st.cache_data(ttl=900)
def fetch_journal():
    rows = iterate_db(JOURNAL_DB)
    journal = []
    for r in rows:
        journal.append({
            "id": r["id"],
            "title": get_prop(r, "Title") or "",
            "date": get_prop(r, "Date") or "",
            "type": get_prop(r, "Type") or "",
            "outcome": get_prop(r, "Outcome") or "",
            "sport": get_prop(r, "Sport") or "",
            "what_worked": get_prop(r, "What Worked") or get_prop(r, "What Happened") or "",
            "what_failed": get_prop(r, "What Failed") or get_prop(r, "Why Win/Loss") or "",
            "lessons": get_prop(r, "Lessons") or get_prop(r, "Lesson") or "",
            "strategy_adj": get_prop(r, "Strategy Adjustment") or get_prop(r, "Action Item") or "",
        })
    return sorted(journal, key=lambda j: j["date"] or "0000", reverse=True)


# ─────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────

with st.spinner("Loading from Notion…"):
    picks = fetch_picks()
    daily = fetch_daily()
    strategies = fetch_strategies()
    journal = fetch_journal()


def compute_bankroll():
    live_settled = [p for p in picks if p["account"] == "LIVE" and p["result"] in ("Won", "Lost")]
    paper_settled = [p for p in picks if p["account"] == "PAPER" and p["result"] in ("Won", "Lost")]
    live_start = 143.0
    live_net = sum(float(p["net"]) for p in live_settled)
    live_current = round(live_start + live_net, 2)
    live_peak = round(max(live_current, 155.0), 2)
    live_dd = round(((live_peak - live_current) / live_peak * 100) if live_peak > 0 else 0, 1)
    paper_start = 500.0
    paper_net = sum(float(p["net"]) for p in paper_settled)
    paper_current = round(paper_start + paper_net, 2)
    paper_peak = round(max(paper_current, 500.0), 2)
    paper_dd = round(((paper_peak - paper_current) / paper_peak * 100) if paper_peak > 0 else 0, 1)
    return {
        "live_current": live_current, "live_peak": live_peak, "live_dd": live_dd,
        "paper_current": paper_current, "paper_peak": paper_peak, "paper_dd": paper_dd,
    }


bk = compute_bankroll()

# ─────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────

st.title("📊 BettingOS Live.v.2 Dashboard")
st.caption(f"Synced from Notion · Auto-refresh every 15 min · "
           f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

total_settled = len([p for p in picks if p["result"] in ("Won", "Lost")])
pending = len([p for p in picks if p["result"] == "Pending"])
if pending == 0:
    st.success(f"✅ All systems green — {total_settled} settled picks, 0 pending")
else:
    st.warning(f"⚠️ {pending} picks pending settlement, {total_settled} settled")

st.subheader("Bankroll")
c1, c2, c3 = st.columns(3)
c1.metric("LIVE Bankroll", f"${bk['live_current']:.2f}",
          delta=f"${bk['live_current'] - bk['live_peak']:+.2f}" if bk['live_dd'] > 0 else "0.00")
c2.metric("LIVE Peak", f"${bk['live_peak']:.2f}")
c3.metric("LIVE Drawdown", f"-{bk['live_dd']:.1f}%")
c4, c5, c6 = st.columns(3)
c4.metric("PAPER Bankroll", f"${bk['paper_current']:.2f}",
          delta=f"${bk['paper_current'] - bk['paper_peak']:+.2f}" if bk['paper_dd'] > 0 else "0.00")
c5.metric("PAPER Peak", f"${bk['paper_peak']:.2f}")
c6.metric("PAPER Drawdown", f"-{bk['paper_dd']:.1f}%")

st.divider()

# ─────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Today", "Picks", "Performance", "Last 7 Days",
    "Strategies", "Journal", "Calibration", "Settings",
])

with tab1:
    st.header("Today")
    today_et = (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
    today_picks = [p for p in picks if p["date"] == today_et]
    if not today_picks:
        st.info(f"No picks for {today_et} yet. Noon-lock fires at 12 PM ET, late-lock at 3 PM ET.")
    else:
        live_today = [p for p in today_picks if p["account"] == "LIVE"]
        paper_today = [p for p in today_picks if p["account"] == "PAPER"]
        cA, cB = st.columns(2)
        cA.metric("LIVE picks today", len(live_today))
        cB.metric("PAPER picks today", len(paper_today))
        if live_today:
            st.subheader("LIVE")
            df = pd.DataFrame(live_today)
            st.dataframe(df[["pick", "tier", "stake", "odds", "strategy", "result", "net"]],
                         use_container_width=True)
        if paper_today:
            with st.expander(f"PAPER ({len(paper_today)} picks)"):
                df = pd.DataFrame(paper_today)
                st.dataframe(df[["pick", "stake", "odds", "strategy", "result", "net"]],
                             use_container_width=True)

with tab2:
    st.header("All Picks")
    cA, cB, cC = st.columns(3)
    acct = cA.selectbox("Account", ["All", "LIVE", "PAPER"])
    res = cB.selectbox("Result", ["All", "Won", "Lost", "Pending", "Push", "Void", "Scratched"])
    sports_avail = sorted(set(p["sport"] for p in picks if p["sport"]))
    sport = cC.selectbox("Sport", ["All"] + sports_avail)
    filt = picks
    if acct != "All":
        filt = [p for p in filt if p["account"] == acct]
    if res != "All":
        filt = [p for p in filt if p["result"] == res]
    if sport != "All":
        filt = [p for p in filt if p["sport"] == sport]
    st.caption(f"Showing {len(filt)} of {len(picks)} picks")
    if filt:
        df = pd.DataFrame(filt)
        st.dataframe(df[["date", "sport", "pick", "account", "tier", "stake", "odds", "result", "net"]],
                     use_container_width=True, height=600)
    else:
        st.info("No picks match filter.")

with tab3:
    st.header("Performance")
    settled = [p for p in picks if p["result"] in ("Won", "Lost")]
    if not settled:
        st.info("No settled picks yet.")
    else:
        live_s = [p for p in settled if p["account"] == "LIVE"]
        paper_s = [p for p in settled if p["account"] == "PAPER"]
        cA, cB = st.columns(2)
        with cA:
            st.subheader("LIVE")
            lw = sum(1 for p in live_s if p["result"] == "Won")
            lt = len(live_s)
            lnet = sum(float(p["net"]) for p in live_s)
            st.metric("Record", f"{lw}W-{lt - lw}L")
            st.metric("Net P/L", f"${lnet:+.2f}")
            st.metric("Hit Rate", f"{(lw / max(1, lt)) * 100:.1f}%")
        with cB:
            st.subheader("PAPER")
            pw = sum(1 for p in paper_s if p["result"] == "Won")
            pt = len(paper_s)
            pnet = sum(float(p["net"]) for p in paper_s)
            st.metric("Record", f"{pw}W-{pt - pw}L")
            st.metric("Net P/L", f"${pnet:+.2f}")
            st.metric("Hit Rate", f"{(pw / max(1, pt)) * 100:.1f}%")
        st.subheader("ROI by Sport")
        sport_agg = {}
        for p in settled:
            s = p["sport"] or "Unknown"
            agg = sport_agg.setdefault(s, {"stake": 0.0, "net": 0.0, "n": 0})
            agg["stake"] += float(p["stake"] or 0)
            agg["net"] += float(p["net"] or 0)
            agg["n"] += 1
        if sport_agg:
            df_sport = pd.DataFrame([
                {"sport": s, "n": a["n"],
                 "stake": round(a["stake"], 2), "net": round(a["net"], 2),
                 "roi_pct": round((a["net"] / a["stake"] * 100) if a["stake"] else 0, 1)}
                for s, a in sport_agg.items()
            ])
            fig = px.bar(df_sport, x="sport", y="roi_pct", color="roi_pct",
                         color_continuous_scale=["red", "white", "green"],
                         title="ROI % by Sport")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_sport, use_container_width=True)

with tab4:
    st.header("Last 7 Days")
    if not daily:
        st.info("No daily data yet.")
    else:
        recent = daily[-7:]
        df = pd.DataFrame(recent)
        if not df.empty:
            fig = px.bar(df, x="date", y="net",
                         color="net",
                         color_continuous_scale=["red", "white", "green"],
                         title="Daily Net P/L (LIVE)")
            st.plotly_chart(fig, use_container_width=True)
            cols = [c for c in ["date", "bankroll_start", "bankroll_end", "net",
                                  "live_w", "live_l", "live_roi",
                                  "paper_w", "paper_l", "paper_roi"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True)

with tab5:
    st.header("Strategies")
    if not strategies:
        st.info("No strategy data yet.")
    else:
        active = [s for s in strategies if (s["status"] or "").upper() in ("ACTIVE", "PROMOTED")]
        archived = [s for s in strategies if (s["status"] or "").upper() in ("ARCHIVED", "KILLED")]
        cA, cB, cC = st.columns(3)
        cA.metric("Active", len(active))
        cB.metric("Archived", len(archived))
        cC.metric("Other status", len(strategies) - len(active) - len(archived))
        if active:
            df = pd.DataFrame(active)

            def badge(row):
                n = int(row["picks"] or 0)
                if n < 30:
                    return "—"
                hr = float(row["hit_rate"] or 0)
                roi = float(row["roi"] or 0)
                if hr > 60 and roi > 5:
                    return "🟢 PROMOTE"
                if hr < 40 and roi < -10:
                    return "🔴 DEMOTE"
                return "—"

            df["Badge"] = df.apply(badge, axis=1)
            cols = [c for c in ["name", "sport", "picks", "won", "lost",
                                  "hit_rate", "net", "roi", "Badge", "last_fired"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, height=600)
            st.caption("PROMOTE/DEMOTE badges require n≥30 settled picks. Below that: insufficient sample.")

with tab6:
    st.header("Journal")
    if not journal:
        st.info("No journal entries yet.")
    else:
        filt_txt = st.text_input("Filter (search title/content)", "")
        items = journal
        if filt_txt:
            f = filt_txt.lower()
            items = [j for j in items if f in (j["title"] + j["what_worked"] + j["what_failed"] + j["lessons"]).lower()]
        st.caption(f"Showing {len(items)} of {len(journal)} entries")
        for entry in items[:50]:
            header = f"{entry['date']} · {entry['type']} · {entry['outcome']} · {entry['title'][:80]}"
            with st.expander(header):
                cA, cB = st.columns(2)
                with cA:
                    st.markdown(f"**🟢 What Worked:**\n\n{entry['what_worked'] or '_—_'}")
                    st.markdown(f"**📘 Lessons:**\n\n{entry['lessons'] or '_—_'}")
                with cB:
                    st.markdown(f"**🔴 What Failed:**\n\n{entry['what_failed'] or '_—_'}")
                    st.markdown(f"**🎯 Strategy Adjustment:**\n\n{entry['strategy_adj'] or '_—_'}")

with tab7:
    st.header("Calibration")
    settled = [p for p in picks if p["result"] in ("Won", "Lost")]
    if not settled:
        st.info("No data for calibration yet. Need 30+ settled picks per bucket.")
    else:
        df = pd.DataFrame(settled)
        df["won_binary"] = (df["result"] == "Won").astype(int)
        overall_hit = df["won_binary"].mean() * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("Settled total", len(settled))
        c2.metric("Overall hit rate", f"{overall_hit:.1f}%")
        c3.metric("Net total", f"${df['net'].sum():+.2f}")
        st.caption("Full predicted-vs-actual bucketing returns once we wire it through the engine.")

with tab8:
    st.header("Settings")
    st.markdown("### System Configuration")
    st.text("LIVE Tier: 1 (1u = $3, Tier 2 graduates at $200)")
    st.text("LIVE Daily Cap: 10% of bankroll")
    st.text("PAPER Daily Cap: 20% of bankroll")
    st.text("PAPER Unit: 1u = $5")
    st.text(f"Active Strategies (canonical): 26")
    st.markdown("### Data Source")
    st.text("Notion REST API (direct urllib) · 4 production DBs")
    st.text("Refresh cadence: 15 min cache (@st.cache_data ttl=900)")
    st.markdown("### Access")
    st.text(f"Public URL: this Streamlit app")
    st.text(f"Backup: http://davidslaptop:8765/dashboard.html (Tailscale private)")
    st.markdown("### Bankroll Math")
    st.text(f"LIVE: ${bk['live_current']:.2f} / Peak ${bk['live_peak']:.2f} / DD -{bk['live_dd']:.1f}%")
    st.text(f"PAPER: ${bk['paper_current']:.2f} / Peak ${bk['paper_peak']:.2f} / DD -{bk['paper_dd']:.1f}%")
    if st.button("🔄 Force refresh from Notion"):
        st.cache_data.clear()
        st.rerun()

# ─────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"BettingOS Live.v.2 · Streamlit Cloud · Auto-cache 15 min · "
    f"{len(picks)} picks · {len(strategies)} strategies · {len(journal)} journal entries"
)

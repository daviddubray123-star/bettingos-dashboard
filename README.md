# BettingOS Dashboard (Streamlit)

Public dashboard for the BettingOS Live.v.2 betting system. Auto-syncs from Notion every 15 minutes.

## Local development

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Fill in your real NOTION_TOKEN in secrets.toml
streamlit run app.py
```

## Deployment

Auto-deploys to Streamlit Cloud on push to `main`:

1. Push this repo to GitHub.
2. Go to https://share.streamlit.io → New app → select repo → main → `app.py`.
3. Pick a subdomain like `bettingos-david.streamlit.app`.
4. After deploy, Settings → Secrets → paste the same content as `.streamlit/secrets.toml`.
5. Wait ~30s for the app to restart with the new secrets.

## Architecture

- Reads 4 Notion DBs: Picks, Daily Dashboard, Strategy Performance, Journal.
- All field mappings handle both v1 and v2 schema names (e.g., `What Worked` OR `What Happened`).
- No PC dependency — runs entirely on Streamlit Cloud.
- 15-min `@st.cache_data` ttl. Manual refresh button on Settings tab.

## Tabs

1. **Today** — today's LIVE + PAPER picks
2. **Picks** — full history with account/result/sport filters
3. **Performance** — LIVE vs PAPER breakdown + ROI by sport chart
4. **Last 7 Days** — daily P/L bar chart + table
5. **Strategies** — 26 canonical active strategies + auto-promote/demote badges (require n≥30)
6. **Journal** — daily reflections with What Worked / Failed / Lessons / Adjustment
7. **Calibration** — top-line hit rate + W-L distribution
8. **Settings** — config summary + manual refresh button

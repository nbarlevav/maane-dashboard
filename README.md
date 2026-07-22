# Machon Maane — Live Campaign Dashboard

A tiny Flask app that renders a live Meta (Facebook/Instagram) ad-campaign dashboard,
pulling fresh numbers from the Meta Marketing API on each page load (short server-side
cache), and emails a daily Hebrew digest. Deployed on the Pi via Coolify, behind
Cloudflare at https://maane.barlevav.com.

All configuration is via environment variables — **no secrets in this repo**:

| Var | Purpose |
|---|---|
| `META_ACCESS_TOKEN` | Meta system-user token (ads_read) |
| `META_AD_ACCOUNT_ID` | `act_…` |
| `MAANE_CAMPAIGN_ID` | the campaign to report on |
| `VALIDATION_BUDGET` | budget ceiling (ILS), default 1500 |
| `LEAD_GOAL` | lead goal, default 200 |
| `CACHE_TTL` | seconds between live pulls, default 180 |
| `RESEND_API_KEY` | for the daily digest email |
| `DIGEST_FROM` / `DIGEST_TO` | digest sender / recipient |
| `DIGEST_HOUR` | hour (Israel time) to send, default 8 |
| `ENABLE_DIGEST` | `1` to enable the daily email |

Run locally: `pip install -r requirements.txt && python app.py`

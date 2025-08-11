## upjobs — Upwork ETL → Supabase → Google Sheets (bi-directional)

- Extract from local WebScrapBook HTML → process → upsert to Supabase → mirror to Google Sheets.
- Edit user fields in Sheets (jobs.saved, search_results.is_applied, job notes, applications); pull changes back to DB.

### 1) Prereqs
- UV (uv package manager) installed
- Hosted Supabase project (URL and anon/service key)
- Google Cloud project with Sheets API enabled
- A Google Sheet to use as the dashboard (copy its ID from the URL)

### 2) Configure environment
1) Copy `.env.example` to `.env` and fill the placeholders:

```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

GOOGLE_SHEET_ID=your_google_sheet_id

# Optional overrides (defaults shown)
# GOOGLE_OAUTH_CLIENT_FILE=/absolute/path/to/credentials/oauth_client_secret.json
# GOOGLE_OAUTH_TOKEN_FILE=/absolute/path/to/credentials/oauth_token.json
```

2) Place OAuth client file
- In Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID (Desktop app) → download JSON.
- Save it to: `credentials/oauth_client_secret.json` (use the override env if you prefer a different location).

### 3) Apply database schema (one-time)
- In Supabase Dashboard → SQL Editor: run the SQL files in `supabase/migrations/` in order (01 → 08).

### 4) Install dependencies
```
uv sync --active
uv run --active playwright install
```

### 5) Commands (copy/paste)
- Run everything in one go (scrape → process → DB → Sheets):
```
uv run --active upjobs run-all
```
  - First run will open a browser to authorize Google; it writes `credentials/oauth_token.json`.

- Only push DB → Sheets (mirror):
```
uv run --active upjobs sheets-push
```

- Only pull Sheets → DB (apply user edits):
```
uv run --active upjobs sheets-pull
```

- Open configured Upwork search URLs in your browser:
```
uv run --active upjobs open-urls
```

- Clean processed JSON artifacts:
```
uv run --active upjobs cleanup
```

### 6) What each command does
- `run-all`: Extract from local HTML → write JSON → flatten → upsert jobs/search_results/scrapes to Supabase → mirror all tabs to Sheets (hiding terminal-status jobs by default).
- `sheets-push`: Read from Supabase and upsert into Sheets tabs (Jobs, SearchResults, ScrapeRequests, JobNotes, Applications, ApplicationStatusHistory).
- `sheets-pull`: Read changed user fields from Sheets and upsert to Supabase (jobs.saved, search_results.is_applied, job_notes, applications; append status history on status change).
- `open-urls`: Open search URLs from `config/search_urls.yml` in the browser.
- `cleanup`: Remove generated processed JSON files.

### 7) Sheets editing model
- Jobs (tab): edit `saved` only. DB-sourced fields are overwritten by push.
- SearchResults: edit `is_applied` only.
- JobNotes: new row → leave `note_id` blank and set `job_id`, `note_text` (optional `author`, `application_id`); edit existing with `note_id` present.
- Applications: new row → leave `application_id` blank and set `job_id` (optional `final_message`, `status`, `submitted_at`, `connects_spent`, `boosted`, `proposal_url`); edit existing with `application_id` present. Status changes append to the history tab.
- ApplicationStatusHistory: read-only mirror of status changes.

### 8) Hiding terminal outcomes in Jobs tab
- By default, `sheets-push` hides any job that has an application with a terminal status `{rejected,lost,withdrawn,accepted,hired,won}`.
- Show all jobs: `uv run --active upjobs sheets-push --no-hide-terminal`.

### 9) Troubleshooting
- 403 when pushing to Sheets on first run: ensure you completed OAuth (a browser window opens) and the Sheet ID is correct.
- No rows in Sheets after push: check `.env` values and that your Supabase DB has data.
- Filename parsing for scrapes: stems like `<timestamp>-<query>-page` (with or without a number) are supported; timestamp is stored when present.


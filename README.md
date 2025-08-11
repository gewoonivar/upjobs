## upjobs — Supabase (hosted) + Google Sheets UI (with AI drafts)

- Run ETL on WebScrapBook-saved Upwork HTML → upsert to Supabase (hosted) → mirror to Google Sheets.
- Mark jobs Saved in Sheets to auto-generate AI draft applications (later).

Quickstart
- Prereqs: UV, a hosted Supabase project, a Google Sheet shared with your service account.
- Copy `.env.example` to `.env` and set:
  - `SUPABASE_URL` (Project Settings → API → URL)
  - `SUPABASE_KEY` (service_role key; server-side only)
  - `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE`
- Apply schema: In Supabase Dashboard → SQL editor, run the files in `supabase/migrations/` in order (01 → 07).
- Install deps: `uv sync`; browsers: `uv run playwright install`.
- Commands: `uv run upjobs run-all`, `uv run upjobs open-urls`, `uv run upjobs cleanup`.

Notes
- You can delete/ignore any local Docker or Supabase CLI config; this repo targets hosted Supabase.
- `SUPABASE_KEY` should be the service_role key for simplest server-side upserts.

See `config/webscrapbook.options.20250808.json` to configure WebScrapBook capture.


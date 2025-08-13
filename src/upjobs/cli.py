from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path

import typer

from upjobs import config, utils
from upjobs.ai import summarize_jobs
from upjobs.connectors import supabase as sbx
from upjobs.connectors.airtable import batch_upsert_jobs, get_jobs_table
from upjobs.connectors.sheets import (
    ensure_worksheet,
    open_spreadsheet,
    upsert_rows,
)
from upjobs.connectors.sheets import (
    get_client as get_gs,
)
from upjobs.connectors.supabase import (
    get_client as get_sb,
)
from upjobs.connectors.supabase import (
    update_scrape_processed,
    upsert_jobs,
    upsert_scrape_request,
    upsert_search_results,
)
from upjobs.processing import process_json_file
from upjobs.scraping import extract_jobs_from_directory

app = typer.Typer(help="Upwork ETL → Supabase → Google Sheets; AI draft generation")


def _dedupe_jobs(rows: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for r in rows:
        jid = r.get("job_id")
        if not jid:
            continue
        by_id[str(jid)] = r
    return list(by_id.values())


def _dedupe_search_results(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for r in rows:
        search_id = r.get("search_id")
        job_id = r.get("job_id")
        if not search_id or not job_id:
            continue
        key = (str(search_id), str(job_id))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


JOBS_HEADERS = [
    "job_id",
    "url",
    "title",
    "description",
    "description_summary",
    "description_summary_model",
    "description_summary_tokens",
    "skills",
    "created_on",
    "published_on",
    "renewed_on",
    "duration_label",
    "connect_price",
    "job_type",
    "engagement",
    "proposals_tier",
    "tier_text",
    "fixed_budget",
    "weekly_budget",
    "hourly_budget_min",
    "hourly_budget_max",
    "currency",
    "client_country",
    "client_total_spent",
    "client_payment_verified",
    "client_total_reviews",
    "client_avg_feedback",
    "is_sts_vector_search_result",
    "relevance_encoded",
    "is_applied",
    "saved",
    "create_date",
]
SR_HEADERS = ["search_id", "job_id", "proposals_tier", "is_applied", "search_job_key"]
SC_HEADERS = ["search_id", "query", "page", "filepath", "query_timestamp", "processed"]

NOTES_HEADERS = ["note_id", "job_id", "application_id", "author", "note_text", "created_at"]
APPS_HEADERS = [
    "application_id",
    "job_id",
    "final_message",
    "status",
    "submitted_at",
    "connects_spent",
    "boosted",
    "proposal_url",
]
HIST_HEADERS = ["history_id", "application_id", "status", "changed_at"]


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "yes", "y", "1"}:
            return True
        if v in {"false", "no", "n", "0"}:
            return False
    return None


def _coerce_int(value: object) -> int | None:
    try:
        s = str(value).strip()
        return int(s) if s != "" else None
    except (TypeError, ValueError):
        return None


@app.command()
def open_urls(file: Path = typer.Option(None, help="YAML file with search URLs")) -> None:
    """Open search URLs in Firefox (first in new window, others in tabs)."""
    urls_file = file or config.SEARCH_URLS_FILE
    urls = utils.load_search_urls(urls_file)
    if not urls:
        typer.echo(f"No URLs found in {urls_file}")
        raise typer.Exit(code=1)
    try:
        browser = webbrowser.get("firefox")
    except webbrowser.Error:
        browser = webbrowser.get()
    browser.open_new(urls[0])
    for url in urls[1:]:
        browser.open_new_tab(url)
    typer.echo("Opened URLs in Firefox")


@app.command()
def cleanup() -> None:
    """Delete generated local artifacts (processed JSON)."""
    utils.cleanup_dir(config.PROCESSED_JSON_DIR)
    typer.echo("Cleaned processed JSON directory")


@app.command()
def run_all(headless: bool = True, timeout_ms: int = 30000) -> None:
    """Extract jobs from local HTML → process → upsert to Supabase."""
    input_dir = utils.get_dynamic_webscrapbook_dir(Path(config.WEBSCRAPBOOK_BASE_DIR))
    config.PROCESSED_JSON_DIR.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Extracting from: {input_dir}")

    # Step 1: Scrape HTML → JSON files
    asyncio.run(
        extract_jobs_from_directory(
            input_dir=input_dir,
            output_dir=config.PROCESSED_JSON_DIR,
            timeout_ms=timeout_ms,
            headless=headless,
        )
    )
    typer.echo("Extracted jobs from local HTML")

    # Step 2: Process JSON → rows
    json_files = sorted(config.PROCESSED_JSON_DIR.glob("*.json"))
    if not json_files:
        typer.echo("No JSON files found to process.")
        raise typer.Exit(code=0)

    sb = get_sb()
    jobs_buffer: list[dict] = []
    search_results_buffer: list[dict] = []
    scrape_requests: list[dict] = []
    for jf in json_files:
        jobs_rows, sr_rows, scrape_req = process_json_file(jf)
        jobs_buffer.extend(jobs_rows)
        search_results_buffer.extend(sr_rows)
        scrape_requests.append(scrape_req)
    typer.echo("Processed JSON files")

    # Step 3: Deduplicate and upsert to Supabase
    jobs_buffer = _dedupe_jobs(jobs_buffer)
    search_results_buffer = _dedupe_search_results(search_results_buffer)

    # Step 3.0: Derive create_date (DD-MM-YYYY) from created_on if missing
    from datetime import datetime

    for j in jobs_buffer:
        if j.get("create_date"):
            continue
        created_on = j.get("created_on")
        if not created_on or not isinstance(created_on, str):
            continue
        iso = created_on.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso)
            # Store ISO (YYYY-MM-DD) for Postgres DATE; format in Sheets as needed
            j["create_date"] = dt.date().isoformat()
        except Exception:
            # leave unset if parsing fails
            pass

    # Step 3.1: Summarize job descriptions
    try:  # noqa: BLE001
        # Preload existing summaries from DB so we don't re-summarize and incur cost
        job_ids = [j.get("job_id") for j in jobs_buffer if j.get("job_id")]
        if job_ids:
            try:  # noqa: BLE001
                existing = (
                    sb.table("jobs")
                    .select("job_id,description_summary")
                    .in_("job_id", job_ids)
                    .execute()
                    .data
                    or []
                )
                id_to_summary = {
                    r.get("job_id"): r.get("description_summary")
                    for r in existing
                    if r.get("description_summary")
                }
                for j in jobs_buffer:
                    jid = j.get("job_id")
                    if jid in id_to_summary:
                        j["description_summary"] = id_to_summary[jid]
            except Exception:  # noqa: BLE001
                pass

        asyncio.run(
            summarize_jobs(
                jobs_buffer,
                max_words=config.AI_SUMMARY_MAX_WORDS,
                model=config.AI_MODEL,
                limit=config.AI_SUMMARIZE_LIMIT,
                concurrency=config.AI_CONCURRENCY,
            )
        )
        typer.echo("Summarized job descriptions")
    except Exception as e:  # noqa: BLE001
        typer.echo(f"Summary step skipped: {e}")

    for s in scrape_requests:
        upsert_scrape_request(sb, s)
    if jobs_buffer:
        upsert_jobs(sb, jobs_buffer)
    if search_results_buffer:
        upsert_search_results(sb, search_results_buffer)
    for s in scrape_requests:
        sid = s.get("search_id")
        if sid:
            update_scrape_processed(sb, sid, True)
    typer.echo("Upserted to Supabase")

    # Push to Google Sheets as part of Run All
    try:  # noqa: BLE001
        sheets_push()  # use default hide_terminal=True
    except Exception as e:  # noqa: BLE001
        typer.echo(f"Sheets push skipped: {e}")

    typer.echo("Pushed to Sheets - DONE")


@app.command()
def process_file(path: Path) -> None:
    """Process a single processed-JSON file → upsert to Supabase.

    Example:
        upjobs process-file "/absolute/path/20250810112529289-data ai engineer-page.json"
    """
    if not path.exists():
        typer.echo(f"File not found: {path}")
        raise typer.Exit(code=1)
    jobs_rows, sr_rows, scrape_req = process_json_file(path)

    sb = get_sb()
    upsert_scrape_request(sb, scrape_req)
    if jobs_rows:
        upsert_jobs(sb, _dedupe_jobs(list(jobs_rows)))
    if sr_rows:
        upsert_search_results(sb, _dedupe_search_results(list(sr_rows)))
    sid = scrape_req.get("search_id")
    if sid:
        update_scrape_processed(sb, sid, True)
    typer.echo(
        f"Processed {len(jobs_rows)} jobs and {len(sr_rows)} search_results from {path.name}"
    )
    typer.echo("Single file upserted to Supabase")


@app.command()
def generate_ai(limit: int = 10) -> None:
    """Generate AI drafts for Saved jobs without applications (scaffold)."""
    typer.echo(f"Generating up to {limit} AI drafts (scaffold)")


@app.command()
def sheets_push(
    hide_terminal: bool = typer.Option(
        True,
        help="Hide jobs having any application with terminal statuses from Jobs tab",
    ),
) -> None:
    """Mirror Supabase tables into Google Sheets tabs."""
    sb = get_sb()
    gs = get_gs()
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID not set")
    ss = open_spreadsheet(gs, config.GOOGLE_SHEET_ID)

    jobs_ws = ensure_worksheet(ss, "Jobs", cols=len(JOBS_HEADERS))
    sr_ws = ensure_worksheet(ss, "SearchResults", cols=len(SR_HEADERS))
    sc_ws = ensure_worksheet(ss, "ScrapeRequests", cols=len(SC_HEADERS))
    notes_ws = ensure_worksheet(ss, "JobNotes", cols=len(NOTES_HEADERS))
    apps_ws = ensure_worksheet(ss, "Applications", cols=len(APPS_HEADERS))
    hist_ws = ensure_worksheet(ss, "ApplicationStatusHistory", cols=len(HIST_HEADERS))

    jobs_rows = sbx.fetch_jobs(sb, limit=20000)
    sr_rows_raw = sbx.fetch_search_results(sb, limit=20000)
    sc_rows = sbx.fetch_scrape_requests(sb, limit=20000)
    notes_rows = sbx.fetch_job_notes(sb, limit=20000)
    apps_rows = sbx.fetch_applications(sb, limit=20000)
    hist_rows = sbx.fetch_application_status_history(sb, limit=20000)

    sr_rows: list[dict] = []
    for r in sr_rows_raw:
        sid, jid = r.get("search_id"), r.get("job_id")
        if sid and jid:
            sr_rows.append({**r, "search_job_key": f"{sid}::{jid}"})

    if hide_terminal and apps_rows:
        terminal = sbx.TERMINAL_APPLICATION_STATUSES
        job_ids_to_hide = {
            str(a["job_id"]) for a in apps_rows if (a.get("status") or "").lower() in terminal
        }
        jobs_rows = [j for j in jobs_rows if str(j.get("job_id")) not in job_ids_to_hide]

    upsert_rows(jobs_ws, JOBS_HEADERS, jobs_rows, key="job_id")
    upsert_rows(sr_ws, SR_HEADERS, sr_rows, key="search_job_key")
    upsert_rows(sc_ws, SC_HEADERS, sc_rows, key="search_id")
    upsert_rows(notes_ws, NOTES_HEADERS, notes_rows, key="note_id")
    upsert_rows(apps_ws, APPS_HEADERS, apps_rows, key="application_id")
    upsert_rows(hist_ws, HIST_HEADERS, hist_rows, key="history_id")

    typer.echo("Sheets push complete")


@app.command()
def sheets_pull() -> None:
    """Apply user edits from Sheets back to Supabase."""
    sb = get_sb()
    gs = get_gs()
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID not set")
    ss = open_spreadsheet(gs, config.GOOGLE_SHEET_ID)

    # Jobs.saved
    jobs_updates: list[dict] = []
    try:
        jobs_records = ss.worksheet("Jobs").get_all_records()
        for r in jobs_records:
            jid = r.get("job_id")
            saved = _coerce_bool(r.get("saved"))
            if jid is None or saved is None:
                continue
            jobs_updates.append({"job_id": str(jid), "saved": bool(saved)})
    except Exception:  # noqa: BLE001
        jobs_records = []
    if jobs_updates:
        sbx.upsert_jobs_saved(sb, _dedupe_jobs(jobs_updates))

    # SearchResults.is_applied
    sr_updates: list[dict] = []
    try:
        sr_records = ss.worksheet("SearchResults").get_all_records()
        for r in sr_records:
            sid = r.get("search_id")
            jid = r.get("job_id")
            is_applied = _coerce_bool(r.get("is_applied"))
            if not sid or not jid or is_applied is None:
                continue
            sr_updates.append(
                {"search_id": str(sid), "job_id": str(jid), "is_applied": bool(is_applied)}
            )
    except Exception:  # noqa: BLE001
        sr_records = []
    if sr_updates:
        sbx.upsert_search_results_is_applied(sb, _dedupe_search_results(sr_updates))

    # JobNotes
    notes_new: list[dict] = []
    notes_update: list[dict] = []
    try:
        notes_records = ss.worksheet("JobNotes").get_all_records()
        for r in notes_records:
            nid = r.get("note_id")
            job_id = r.get("job_id")
            app_id = r.get("application_id")
            author = r.get("author")
            note_text = r.get("note_text")
            if nid:
                notes_update.append(
                    {
                        "note_id": nid,
                        "note_text": note_text,
                        "author": author,
                        "application_id": app_id,
                    }
                )
            else:
                if job_id and note_text:
                    notes_new.append(
                        {
                            "job_id": job_id,
                            "note_text": note_text,
                            "author": author,
                            "application_id": app_id,
                        }
                    )
    except Exception:  # noqa: BLE001
        notes_records = []
    if notes_new:
        sbx.insert_job_notes(sb, notes_new)
    if notes_update:
        sbx.update_job_notes(sb, notes_update)

    # Applications
    apps_new: list[dict] = []
    apps_update: list[dict] = []
    try:
        apps_records = ss.worksheet("Applications").get_all_records()
        for r in apps_records:
            app_id = r.get("application_id")
            job_id = r.get("job_id")
            final_message = r.get("final_message")
            status = (r.get("status") or "").strip().lower() or None
            submitted_at = r.get("submitted_at")
            connects_spent = _coerce_int(r.get("connects_spent"))
            boosted = _coerce_bool(r.get("boosted"))
            proposal_url = r.get("proposal_url")

            if app_id:
                apps_update.append(
                    {
                        "application_id": app_id,
                        "final_message": final_message,
                        "status": status,
                        "submitted_at": submitted_at,
                        "connects_spent": connects_spent,
                        "boosted": boosted,
                        "proposal_url": proposal_url,
                    }
                )
            else:
                if job_id:
                    apps_new.append(
                        {
                            "job_id": job_id,
                            "final_message": final_message,
                            "status": status,
                            "submitted_at": submitted_at,
                            "connects_spent": connects_spent,
                            "boosted": boosted,
                            "proposal_url": proposal_url,
                        }
                    )
    except Exception:  # noqa: BLE001
        apps_records = []

    if apps_new:
        sbx.insert_applications(sb, apps_new)

    if apps_update:
        before_status = sbx.get_application_status_map(sb)
        sbx.update_applications(sb, apps_update)
        changed: list[tuple[str, str]] = []
        for u in apps_update:
            app_id = str(u["application_id"])
            new_status = (u.get("status") or "").lower()
            old_status = (before_status.get(app_id) or "").lower()
            if new_status and new_status != old_status:
                changed.append((app_id, new_status))
        if changed:
            sbx.insert_status_history(sb, changed)

    typer.echo(
        f"Sheets pull complete (jobs.saved: {len(jobs_updates)}, "
        f"search_results.is_applied: {len(sr_updates)}, "
        f"notes: +{len(notes_new)}/~{len(notes_update)}, apps: +{len(apps_new)}/~{len(apps_update)})"
    )


@app.command()
def airtable_push() -> None:
    """Push the Supabase jobs table to Airtable (upsert by job_id)."""
    sb = get_sb()
    jobs_rows = sbx.fetch_jobs(sb, limit=20000)
    table = get_jobs_table()
    batch_upsert_jobs(table, jobs_rows, batch_size=10)
    typer.echo(f"Airtable push complete (jobs: {len(jobs_rows)})")


if __name__ == "__main__":
    app()

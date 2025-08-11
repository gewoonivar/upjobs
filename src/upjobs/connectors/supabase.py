from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from supabase import Client, create_client

from .. import config


def get_client() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL/KEY not configured")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def upsert_jobs(client: Client, jobs: Iterable[dict[str, Any]]) -> None:
    rows = list(jobs)
    if not rows:
        return
    client.table("jobs").upsert(rows).execute()


def upsert_scrape_request(client: Client, scrape: dict[str, Any]) -> None:
    client.table("scrape_requests").upsert(scrape).execute()


def update_scrape_processed(client: Client, search_id: str, processed: bool) -> None:
    client.table("scrape_requests").update({"processed": processed}).eq(
        "search_id", search_id
    ).execute()


def upsert_search_results(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    payload = list(rows)
    if not payload:
        return
    client.table("search_results").upsert(payload, on_conflict="search_id,job_id").execute()


def get_saved_jobs_without_app(client: Client, limit: int = 50) -> List[dict[str, Any]]:
    # Jobs that are saved but have no application associated
    # Using a left join via RPC is more complex; fetch simply and filter client-side for scaffold
    saved = (
        client.table("jobs")
        .select("job_id,title,description,client_country,currency,job_type,skills,proposals_tier")
        .eq("saved", True)
        .limit(limit)
        .execute()
    )
    # In a real implementation, exclude those having an application
    return saved.data or []


# Sheets sync helpers

TERMINAL_APPLICATION_STATUSES = {"rejected", "lost", "withdrawn", "accepted", "hired", "won"}


def fetch_jobs(client: Client, limit: int = 20000) -> List[dict[str, Any]]:
    cols = (
        "job_id,url,title,description,skills,created_on,published_on,renewed_on,"
        "duration_label,connect_price,job_type,engagement,proposals_tier,tier_text,"
        "fixed_budget,weekly_budget,hourly_budget_min,hourly_budget_max,currency,"
        "client_country,client_total_spent,client_payment_verified,client_total_reviews,"
        "client_avg_feedback,is_sts_vector_search_result,relevance_encoded,is_applied,saved"
    )
    return (client.table("jobs").select(cols).limit(limit).execute().data) or []


def fetch_search_results(client: Client, limit: int = 20000) -> List[dict[str, Any]]:
    return (
        client.table("search_results")
        .select("search_id,job_id,proposals_tier,is_applied")
        .limit(limit)
        .execute()
        .data
    ) or []


def fetch_scrape_requests(client: Client, limit: int = 20000) -> List[dict[str, Any]]:
    return (
        client.table("scrape_requests")
        .select("search_id,query,page,filepath,query_timestamp,processed")
        .limit(limit)
        .execute()
        .data
    ) or []


def fetch_applications(client: Client, limit: int = 20000) -> List[dict[str, Any]]:
    cols = "application_id,job_id,final_message,status,submitted_at,connects_spent,boosted,proposal_url"
    return (client.table("applications").select(cols).limit(limit).execute().data) or []


def fetch_application_status_history(client: Client, limit: int = 20000) -> List[dict[str, Any]]:
    cols = "history_id,application_id,status,changed_at"
    return (
        client.table("application_status_history").select(cols).limit(limit).execute().data
    ) or []


def fetch_job_notes(client: Client, limit: int = 20000) -> List[dict[str, Any]]:
    cols = "note_id,job_id,application_id,author,note_text,created_at"
    return (client.table("job_notes").select(cols).limit(limit).execute().data) or []


def upsert_jobs_saved(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    payload = [
        {"job_id": str(r["job_id"]), "saved": bool(r["saved"])}
        for r in rows
        if r.get("job_id") is not None and r.get("saved") is not None
    ]
    if payload:
        client.table("jobs").upsert(payload, on_conflict="job_id").execute()


def upsert_search_results_is_applied(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    payload = [
        {
            "search_id": str(r["search_id"]),
            "job_id": str(r["job_id"]),
            "is_applied": bool(r["is_applied"]),
        }
        for r in rows
        if r.get("search_id") and r.get("job_id") and r.get("is_applied") is not None
    ]
    if payload:
        client.table("search_results").upsert(payload, on_conflict="search_id,job_id").execute()


def insert_job_notes(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    payload = []
    for r in rows:
        job_id = r.get("job_id")
        note_text = r.get("note_text")
        if not job_id or not note_text:
            continue
        payload.append(
            {
                "job_id": str(job_id),
                "note_text": note_text,
                "author": r.get("author") or "user",
                "application_id": r.get("application_id") or None,
            }
        )
    if payload:
        client.table("job_notes").insert(payload).execute()


def update_job_notes(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    for r in rows:
        nid = r.get("note_id")
        if not nid:
            continue
        update_fields = {k: r[k] for k in ("note_text", "author", "application_id") if k in r}
        if not update_fields:
            continue
        client.table("job_notes").update(update_fields).eq("note_id", nid).execute()


def insert_applications(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    payload = []
    for r in rows:
        job_id = r.get("job_id")
        if not job_id:
            continue
        payload.append(
            {
                "job_id": str(job_id),
                "final_message": r.get("final_message"),
                "status": (r.get("status") or "draft"),
                "submitted_at": r.get("submitted_at"),
                "connects_spent": r.get("connects_spent"),
                "boosted": r.get("boosted"),
                "proposal_url": r.get("proposal_url"),
            }
        )
    if payload:
        client.table("applications").insert(payload).execute()


def update_applications(client: Client, rows: Iterable[dict[str, Any]]) -> None:
    for r in rows:
        app_id = r.get("application_id")
        if not app_id:
            continue
        update_fields = {
            k: r.get(k)
            for k in {
                "final_message",
                "status",
                "submitted_at",
                "connects_spent",
                "boosted",
                "proposal_url",
            }
            if k in r
        }
        if not update_fields:
            continue
        client.table("applications").update(update_fields).eq("application_id", app_id).execute()


def get_application_status_map(client: Client) -> Dict[str, str]:
    apps = (
        client.table("applications").select("application_id,status").limit(20000).execute().data
    ) or []
    return {
        str(a["application_id"]): (a.get("status") or "") for a in apps if a.get("application_id")
    }


def insert_status_history(client: Client, rows: Iterable[Tuple[str, str]]) -> None:
    """Insert application status history rows.

    rows: iterable of (application_id, new_status)
    """
    payload = []
    for app_id, status in rows:
        if not app_id or not status:
            continue
        payload.append({"application_id": str(app_id), "status": status})
    if payload:
        client.table("application_status_history").insert(payload).execute()

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from pyairtable import Table

from .. import config


def get_jobs_table() -> Table:
    if not config.AIRTABLE_API_KEY or not config.AIRTABLE_BASE_ID:
        raise RuntimeError("Airtable not configured: set AIRTABLE_API_KEY and AIRTABLE_BASE_ID")
    return Table(config.AIRTABLE_API_KEY, config.AIRTABLE_BASE_ID, config.AIRTABLE_JOBS_TABLE)


def _normalize_job_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map Supabase jobs row to Airtable fields. Keep types Airtable-friendly.

    - Lists → comma-joined string
    - Dicts → JSON string
    - Keep core scalar fields as-is
    """

    def _list_to_str(v: Any) -> Any:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return v

    def _dict_to_json(v: Any) -> Any:
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return v

    fields: Dict[str, Any] = {
        "job_id": row.get("job_id"),
        "url": row.get("url"),
        "title": row.get("title"),
        "description": row.get("description"),
        "skills": _list_to_str(row.get("skills")),
        "created_on": row.get("created_on"),
        "published_on": row.get("published_on"),
        "renewed_on": row.get("renewed_on"),
        "duration_label": row.get("duration_label"),
        "connect_price": row.get("connect_price"),
        "job_type": row.get("job_type"),
        "engagement": row.get("engagement"),
        "proposals_tier": row.get("proposals_tier"),
        "tier_text": row.get("tier_text"),
        "fixed_budget": row.get("fixed_budget"),
        "weekly_budget": row.get("weekly_budget"),
        "hourly_budget_min": row.get("hourly_budget_min"),
        "hourly_budget_max": row.get("hourly_budget_max"),
        "currency": row.get("currency"),
        "client_country": row.get("client_country"),
        "client_total_spent": row.get("client_total_spent"),
        "client_payment_verified": row.get("client_payment_verified"),
        "client_total_reviews": row.get("client_total_reviews"),
        "client_avg_feedback": row.get("client_avg_feedback"),
        "is_sts_vector_search_result": row.get("is_sts_vector_search_result"),
        "relevance_encoded": _dict_to_json(row.get("relevance_encoded")),
        "is_applied": row.get("is_applied"),
        "saved": row.get("saved"),
    }
    # Drop None values to keep Airtable clean
    return {k: v for k, v in fields.items() if v is not None}


def batch_upsert_jobs(
    table: Table, rows: Iterable[Dict[str, Any]], *, batch_size: int = 10
) -> None:
    """Upsert jobs into Airtable keyed by job_id using batch_upsert.

    Requires an Airtable field named 'job_id' configured as the external key.
    """
    records: List[Dict[str, Any]] = [_normalize_job_row(r) for r in rows]
    if not records:
        return
    for i in range(0, len(records), batch_size):
        chunk_fields = records[i : i + batch_size]
        # pyairtable expects [{"fields": {...}}, ...]
        chunk_wrapped = [{"fields": f} for f in chunk_fields]
        table.batch_upsert(chunk_wrapped, key_fields=["job_id"])  # type: ignore[arg-type]

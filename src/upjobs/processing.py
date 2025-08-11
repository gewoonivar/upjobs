from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

HTML_TAG_RE = re.compile(r"<.*?>")


def _strip_html(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(HTML_TAG_RE, " ", text).strip()


def flatten_record(record: Dict[str, Any]) -> Dict[str, Any]:
    def strip_html(text: Any) -> Any:
        return re.sub(r"<.*?>", "", text) if isinstance(text, str) else text

    def after_last_dot(s: Any) -> Any:
        return s.rsplit(".", 1)[-1] if isinstance(s, str) and "." in s else s

    def between_underscores(s: Any) -> Any:
        if not isinstance(s, str):
            return s
        parts = s.split("_")
        return parts[1] if len(parts) > 2 else s

    def safe_float(val: Any) -> float | None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_job_type(value: Any) -> str | None:
        return {1: "fixed", 2: "hourly"}.get(value)

    def extract_skill_names(attrs: Any) -> list[str]:
        if not isinstance(attrs, list):
            return []
        return [a.get("prettyName") for a in attrs if isinstance(a, dict) and a.get("prettyName")]

    job_id = record.get("uid") or record.get("jobId") or record.get("id")
    url = None
    if record.get("ciphertext"):
        url = f"https://www.upwork.com/jobs/{record.get('ciphertext')}"
    else:
        url = record.get("url") or record.get("jobLink")

    # Currency
    currency = (
        (record.get("amount") or {}).get("currencyCode")
        or (record.get("hourlyBudget") or {}).get("currencyCode")
        or "USD"
    )

    # Skills: prefer attrs[].prettyName; fallback to record["skills"]
    skills = extract_skill_names(record.get("attrs"))
    if not skills and isinstance(record.get("skills"), list):
        skills = [
            s.get("prettyName") or s.get("name") for s in record["skills"] if isinstance(s, dict)
        ]

    # Engagement
    engagement = record.get("engagement")
    if not engagement and isinstance(record.get("posting"), dict):
        engagement = record["posting"].get("engagement")

    # Client
    client = record.get("client") or {}
    client_country = None
    if isinstance(client, dict):
        loc = client.get("location") or {}
        client_country = loc.get("country") if isinstance(loc, dict) else client.get("country")
    client_total_spent = safe_float(client.get("totalSpent"))
    client_payment_verified = client.get("isPaymentVerified")
    if client_payment_verified is None:
        client_payment_verified = client.get("paymentVerificationStatus") in ("VERIFIED", True)
    client_total_reviews = client.get("totalReviews")
    client_avg_feedback = client.get("totalFeedback") or client.get("rating")

    # Budgets
    amount = record.get("amount") or {}
    hourly_budget = record.get("hourlyBudget") or {}
    weekly_budget = (record.get("weeklyBudget") or {}).get("amount")

    # STS flag, relevance
    is_sts = record.get("isSTSVectorSearchResult")
    if is_sts is None:
        is_sts = record.get("isStsVectorSearchResult")
    relevance = record.get("relevanceEncoded")
    if isinstance(relevance, str):
        try:
            relevance = json.loads(relevance)
        except Exception:
            pass

    return {
        "job_id": str(job_id) if job_id is not None else None,
        "url": url,
        "title": strip_html(record.get("title")),
        "description": strip_html(record.get("description")),
        "skills": skills,
        "created_on": record.get("createdOn"),
        "published_on": record.get("publishedOn"),
        "renewed_on": record.get("renewedOn"),
        "duration_label": record.get("durationLabel"),
        "connect_price": record.get("connectPrice"),
        "job_type": get_job_type(record.get("type")),
        "engagement": after_last_dot(engagement),
        "proposals_tier": after_last_dot(record.get("proposalsTier")),
        "tier_text": between_underscores(record.get("tierText")),
        "fixed_budget": amount.get("amount"),
        "weekly_budget": weekly_budget,
        "hourly_budget_min": hourly_budget.get("min"),
        "hourly_budget_max": hourly_budget.get("max"),
        "currency": currency,
        "client_country": client_country,
        "client_total_spent": client_total_spent,
        "client_payment_verified": client_payment_verified,
        "client_total_reviews": client_total_reviews,
        "client_avg_feedback": client_avg_feedback,
        "is_sts_vector_search_result": is_sts,
        "relevance_encoded": relevance,
        "is_applied": bool(record.get("isApplied", False)),
    }


def parse_filename_metadata(filepath: Path) -> dict[str, Any]:
    """
    Extracts search_id, query, page, query_timestamp from filenames like:
      <search_id>-<query>-page.json
      <search_id>-<query>-page<page>.json
    Falls back to <stem> only if no match.
    """
    filename = Path(filepath).name

    # Try strict: requires page digits
    m = re.match(r"^(?P<search_id>\d{14,17})-(?P<query>.*?)-page(?P<page>\d+)\.json$", filename)
    if not m:
        # Relaxed: allows '-page' without digits
        m = re.match(r"^(?P<search_id>\d{14,17})-(?P<query>.*?)-page(?:\.json)?$", filename)

    if m:
        gd = m.groupdict()
        search_id = gd.get("search_id")
        query = gd.get("query")
        page_str = gd.get("page") or ""
        page = int(page_str) if page_str.isdigit() else None

        query_ts = None
        try:
            # search_id is a timestamp like 20250810122108430
            query_ts = datetime.strptime(search_id, "%Y%m%d%H%M%S%f").replace(tzinfo=timezone.utc)
        except Exception:
            pass

        return {
            "search_id": f"{search_id}-{query}-page{page}"
            if page is not None
            else f"{search_id}-{query}-page",
            "query_timestamp": query_ts.isoformat(),
            "query": query,
            "page": page,
        }

    # Fallback (keep current behavior)
    stem = Path(filepath).stem
    return {"search_id": stem, "query_timestamp": None, "query": None, "page": None}


def process_json_file(
    path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Load a JSON file, flatten jobs, and build search_results rows.

    Returns (jobs_rows, search_results_rows, scrape_req_meta)
    """
    meta = parse_filename_metadata(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw_jobs = data if isinstance(data, list) else data.get("jobs", [])
    flattened = [flatten_record(r) for r in raw_jobs if isinstance(r, dict)]

    # de-duplicate by job_id
    seen: set[str] = set()
    unique_jobs: list[dict[str, Any]] = []
    for j in flattened:
        jid = j.get("job_id")
        if not jid or jid in seen:
            continue
        seen.add(jid)
        unique_jobs.append(j)

    search_results_rows: list[dict[str, Any]] = [
        {
            "search_id": meta.get("search_id"),
            "job_id": j.get("job_id"),
            "proposals_tier": j.get("proposals_tier"),
            "is_applied": j.get("is_applied", False),
        }
        for j in unique_jobs
        if j.get("job_id")
    ]

    scrape_req = {
        "search_id": meta.get("search_id"),
        "query": meta.get("query"),
        "page": meta.get("page"),
        "filepath": str(path),
        "query_timestamp": meta.get("query_timestamp"),
    }

    return unique_jobs, search_results_rows, scrape_req

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from playwright.async_api import async_playwright, Page


def _extract_jobs_from_nuxt_object(nuxt_obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Try known paths inside __NUXT__ to find a jobs list.

    Returns an empty list if not found.
    """
    candidates: list[Iterable[dict[str, Any]] | None] = []
    # Common Nuxt state shapes observed in Upwork
    state = nuxt_obj.get("state") or {}
    if isinstance(state, dict):
        jobs_search = state.get("jobsSearch") or {}
        if isinstance(jobs_search, dict):
            candidates.append(jobs_search.get("jobs"))
        feed_best_match = state.get("feedBestMatch") or {}
        if isinstance(feed_best_match, dict):
            candidates.append(feed_best_match.get("jobs"))

    # Fallback: scan for a top-level list of dicts that look like jobs
    for _, value in nuxt_obj.items():
        if isinstance(value, list) and value and isinstance(value[0], dict) and (
            "jobId" in value[0] or "uid" in value[0] or "title" in value[0]
        ):
            candidates.append(value)

    for cand in candidates:
        if isinstance(cand, list):
            return [item for item in cand if isinstance(item, dict)]
    return []


async def extract_from_html(page: Page, html_path: Path, timeout_ms: int = 30000) -> list[dict]:
    """Navigate to a local HTML file and return a list of job dicts from window.__NUXT__.

    Uses page.goto('file://...') for better script execution fidelity than set_content.
    """
    file_url = f"file://{Path(html_path).resolve()}"
    await page.goto(file_url, wait_until="load", timeout=timeout_ms)
    nuxt = await page.evaluate("() => window.__NUXT__ || null")
    if not isinstance(nuxt, dict):
        return []
    return _extract_jobs_from_nuxt_object(nuxt)


async def extract_jobs_from_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    timeout_ms: int = 30000,
    headless: bool = True,
) -> None:
    """Extract jobs from all .html files in input_dir and write JSON files to output_dir.

    Output filenames mirror input stems with .json extension.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(input_dir.glob("*.html"))
    if not html_files:
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        try:
            for html_path in html_files:
                jobs = await extract_from_html(page, html_path, timeout_ms=timeout_ms)
                out_path = output_dir / f"{html_path.stem}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump({"jobs": jobs}, f, ensure_ascii=False)
        finally:
            await browser.close()



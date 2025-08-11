from __future__ import annotations

import asyncio
from typing import Any, Iterable, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import AsyncOpenAI

from . import config


def _build_jinja_env() -> Environment:
    # templates/ directory at project root
    loader = FileSystemLoader(str(config.PROJECT_ROOT / "templates" / "prompts"))
    return Environment(loader=loader, autoescape=select_autoescape(enabled_extensions=("j2",)))


def render_summary_prompt(job: dict[str, Any], *, max_words: int) -> str:
    env = _build_jinja_env()
    tmpl = env.get_template("job_summary.j2")
    return tmpl.render(
        title=job.get("title"),
        duration_label=job.get("duration_label"),
        fixed_budget=job.get("fixed_budget"),
        hourly_min=job.get("hourly_budget_min"),
        hourly_max=job.get("hourly_budget_max"),
        currency=job.get("currency"),
        client_country=job.get("client_country"),
        client_payment_verified=job.get("client_payment_verified"),
        description=job.get("description"),
        max_words=max_words,
    )


async def _summarize_one(client: AsyncOpenAI, prompt: str, model: str) -> tuple[Optional[str], int]:
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise assistant summarizing Upwork job descriptions for fast triage.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
        return text, total_tokens
    except Exception:
        return None, 0


async def summarize_jobs(
    jobs: List[dict[str, Any]],
    *,
    max_words: int,
    model: str,
    limit: int,
    concurrency: int = 5,
) -> None:
    if not config.OPENAI_API_KEY:
        return
    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    sem = asyncio.Semaphore(concurrency)

    tasks: List[asyncio.Task] = []
    count = 0
    for job in jobs:
        if count >= limit:
            break
        if job.get("description_summary") or not job.get("description"):
            continue

        prompt = render_summary_prompt(job, max_words=max_words)

        async def run(j: dict[str, Any], p: str) -> None:
            async with sem:
                text, used = await _summarize_one(client, p, model)
                if text:
                    j["description_summary"] = text
                    j["description_summary_model"] = model
                    j["description_summary_tokens"] = used

        tasks.append(asyncio.create_task(run(job, prompt)))
        count += 1

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

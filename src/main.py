import html
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from cv_loader import load_cv
from fetcher import fetch_from_source
from job import Job
from matcher import score_match
from notifier import send_telegram
from state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
VALIDATED_PATH = ROOT / "sources.validated.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def load_validated_sources() -> list[dict]:
    if not VALIDATED_PATH.exists():
        return []
    data = yaml.safe_load(VALIDATED_PATH.read_text(encoding="utf-8")) or {}
    return data.get("sources", []) or []


def build_message(job: Job, score: int, reason: str) -> str:
    title = html.escape(job.title)
    if job.company:
        title += f" — {html.escape(job.company)}"
    if job.location:
        title += f" ({html.escape(job.location)})"

    lines = [
        f"🎯 <b>Match {score}%</b>",
        f"📌 <b>Title:</b> {title}",
        f"💡 <b>Reason:</b> {html.escape(reason)}",
        f"🔗 <b>Link Apply:</b> {job.url}",
    ]
    return "\n".join(lines)


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_all_jobs(sources: list[dict]) -> list[list[Job]]:
    per_source = []
    for entry in sources:
        label = entry.get("url", "?")
        try:
            source_jobs = fetch_from_source(entry)
            logger.info("[%s] %d jobs found", label, len(source_jobs))
            per_source.append(source_jobs)
        except Exception as exc:
            logger.error("[%s] error: %s", label, exc)
            per_source.append([])
    return per_source


def interleave(job_lists: list[list[Job]]) -> list[Job]:
    result = []
    index = 0
    while True:
        added_any = False
        for jobs in job_lists:
            if index < len(jobs):
                result.append(jobs[index])
                added_any = True
        if not added_any:
            break
        index += 1
    return result


def main() -> None:
    load_dotenv()
    config = load_config()
    threshold = config.get("threshold", 80)
    matching = config.get("matching", {}) or {}
    requests_per_minute = matching.get("requests_per_minute", 5)
    max_per_run = matching.get("max_per_run", 40)
    max_per_day = matching.get("max_per_day")
    max_tokens_per_day = matching.get("max_tokens_per_day")
    min_interval = 60 / requests_per_minute if requests_per_minute > 0 else 0

    sources = load_validated_sources()
    if not sources:
        logger.info(
            "No validated sources yet (%s is empty or missing). "
            "Add URLs to sources.yaml, then run: python src/validate_sources.py",
            VALIDATED_PATH.name,
        )
        return

    state = load_state()
    seen = set(state.get("seen_ids", []))
    cv_text = load_cv()

    today = today_utc()
    if state.get("matcher_date") != today:
        state["matcher_date"] = today
        state["matcher_count"] = 0
        state["tokens_used_today"] = 0
    matcher_count = state.get("matcher_count", 0)
    tokens_used_today = state.get("tokens_used_today", 0)

    per_source_jobs = fetch_all_jobs(sources)
    all_jobs = [job for jobs in per_source_jobs for job in jobs]

    skipped_no_url = 0
    new_per_source = []
    for jobs in per_source_jobs:
        filtered = []
        for job in jobs:
            if job.id in seen:
                continue
            if not job.url:
                seen.add(job.id)
                skipped_no_url += 1
                continue
            filtered.append(job)
        new_per_source.append(filtered)

    new_jobs = interleave(new_per_source)
    logger.info("Total jobs: %d, new: %d", len(all_jobs), len(new_jobs))
    if skipped_no_url:
        logger.info("Skipped %d job(s) with no application link (not actionable).", skipped_no_url)

    budget = max_per_run
    if max_per_day is not None:
        remaining_today = max(max_per_day - matcher_count, 0)
        if remaining_today <= 0:
            logger.info(
                "Daily AI matching budget (%d) already used today (UTC). "
                "Skipping matching until it resets tomorrow.",
                max_per_day,
            )
        budget = min(budget, remaining_today)

    if len(new_jobs) > budget:
        logger.info(
            "Limiting to %d job(s) this run (rate/daily budget); "
            "the rest will be picked up in later runs.",
            budget,
        )
    new_jobs = new_jobs[:budget]

    notified = 0
    for index, job in enumerate(new_jobs):
        if max_tokens_per_day is not None and tokens_used_today >= max_tokens_per_day:
            logger.info(
                "Daily AI token budget (%d) reached; stopping for today to avoid "
                "hitting your provider's hard limit.",
                max_tokens_per_day,
            )
            break

        if index > 0 and min_interval > 0:
            time.sleep(min_interval)

        try:
            result = score_match(cv_text, job)
        except Exception as exc:
            logger.error("[matcher] error for %s: %s", job.id, exc)
            continue

        matcher_count += 1
        tokens_used_today += result.get("tokens_used", 0)
        seen.add(job.id)
        score = result["score"]
        logger.info("  - %s @ %s: %d%%", job.title, job.company, score)

        if score >= threshold:
            try:
                send_telegram(build_message(job, score, result["reason"]))
                notified += 1
            except Exception as exc:
                logger.error("[notifier] error for %s: %s", job.id, exc)

    state["seen_ids"] = list(seen)
    state["matcher_count"] = matcher_count
    state["tokens_used_today"] = tokens_used_today
    save_state(state)

    budget_parts = []
    if max_per_day:
        budget_parts.append(f"{matcher_count}/{max_per_day} AI matches")
    if max_tokens_per_day:
        budget_parts.append(f"{tokens_used_today}/{max_tokens_per_day} tokens")
    budget_note = f" ({', '.join(budget_parts)} used today)" if budget_parts else ""
    logger.info("Done. %d notification(s) sent.%s", notified, budget_note)


if __name__ == "__main__":
    main()

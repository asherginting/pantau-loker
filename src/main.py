import html
import logging
import time
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
    return (
        f"🎯 <b>Match {score}%</b> - {html.escape(job.title)}\n"
        f"🏢 {html.escape(job.company)}\n"
        f"📍 {html.escape(job.location)}\n"
        f"💡 {html.escape(reason)}\n"
        f"🔗 {job.url}"
    )


def fetch_all_jobs(sources: list[dict]) -> list[Job]:
    jobs = []
    for entry in sources:
        label = entry.get("url", "?")
        try:
            source_jobs = fetch_from_source(entry)
            logger.info("[%s] %d jobs found", label, len(source_jobs))
            jobs.extend(source_jobs)
        except Exception as exc:
            logger.error("[%s] error: %s", label, exc)
    return jobs


def main() -> None:
    load_dotenv()
    config = load_config()
    threshold = config.get("threshold", 80)
    matching = config.get("matching", {}) or {}
    requests_per_minute = matching.get("requests_per_minute", 5)
    max_per_run = matching.get("max_per_run", 40)
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

    all_jobs = fetch_all_jobs(sources)
    new_jobs = [job for job in all_jobs if job.id not in seen]
    logger.info("Total jobs: %d, new: %d", len(all_jobs), len(new_jobs))

    if len(new_jobs) > max_per_run:
        logger.info(
            "Limiting to %d job(s) this run to respect the AI rate limit; "
            "the rest will be picked up in later runs.",
            max_per_run,
        )
        new_jobs = new_jobs[:max_per_run]

    notified = 0
    for index, job in enumerate(new_jobs):
        if index > 0 and min_interval > 0:
            time.sleep(min_interval)

        try:
            result = score_match(cv_text, job)
        except Exception as exc:
            logger.error("[matcher] error for %s: %s", job.id, exc)
            continue

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
    save_state(state)
    logger.info("Done. %d notification(s) sent.", notified)


if __name__ == "__main__":
    main()

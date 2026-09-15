import logging
import os
import time
from pathlib import Path

import yaml

from detector import validate_source

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "sources.yaml"
MANUAL_PATH = ROOT / "sources.manual.yaml"
VALIDATED_PATH = ROOT / "sources.validated.yaml"
CONFIG_PATH = ROOT / "config.yaml"

DEFAULT_MAX_SOURCES = 50
DEFAULT_DELAY_SECONDS = 1.5


def load_urls() -> list[str]:
    if not SOURCES_PATH.exists():
        return []
    data = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8")) or {}
    return [str(url).strip() for url in (data.get("urls") or []) if url]


def load_manual_entries() -> list[dict]:
    if not MANUAL_PATH.exists():
        return []
    data = yaml.safe_load(MANUAL_PATH.read_text(encoding="utf-8")) or {}
    return data.get("sources", []) or []


def load_limits() -> tuple[int, float]:
    if not CONFIG_PATH.exists():
        return DEFAULT_MAX_SOURCES, DEFAULT_DELAY_SECONDS
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    validation = config.get("validation", {}) or {}
    return (
        validation.get("max_sources", DEFAULT_MAX_SOURCES),
        validation.get("request_delay_seconds", DEFAULT_DELAY_SECONDS),
    )


def write_step_summary(results: list[dict], manual_count: int) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    passed = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] != "ok"]

    lines = [
        "## Validate Sources summary",
        "",
        f"**{len(passed)} of {len(results)}** URL(s) passed"
        + (f", plus **{manual_count}** manual override(s)" if manual_count else "")
        + ".",
        "",
        "| Status | URL | Detail |",
        "|---|---|---|",
    ]
    for r in passed:
        lines.append(f"| ✅ OK | {r['url']} | {r['detail']} |")
    for r in skipped:
        lines.append(f"| ❌ SKIP | {r['url']} | {r['detail']} |")

    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    urls = load_urls()
    manual_entries = load_manual_entries()

    if not urls and not manual_entries:
        logger.info("No URLs in %s yet. Add some under 'urls:'.", SOURCES_PATH.name)
        return

    max_sources, delay = load_limits()
    if len(urls) > max_sources:
        logger.warning(
            "Found %d URLs, but the per-run limit is %d "
            "(config.yaml -> validation.max_sources). Only the first %d will be validated.",
            len(urls),
            max_sources,
            max_sources,
        )
        urls = urls[:max_sources]

    logger.info("Validating %d URL(s)...\n", len(urls))
    ok_entries = []
    results = []
    for index, url in enumerate(urls, start=1):
        result = validate_source(url)
        if result["status"] == "ok":
            entry = result["entry"]
            detail = f"{entry['method']} — {result['sample_count']} job(s) found right now"
            logger.info("[%d/%d] OK   %s", index, len(urls), url)
            logger.info("           -> method: %s, %d job(s) found right now", entry["method"], result["sample_count"])
            ok_entries.append(entry)
        else:
            detail = result["reason"]
            logger.info("[%d/%d] SKIP %s", index, len(urls), url)
            logger.info("           -> %s", detail)

        results.append({"url": url, "status": result["status"], "detail": detail})

        if index < len(urls):
            time.sleep(delay)

    if manual_entries:
        logger.info("\nAdding %d manually configured source(s) from %s.", len(manual_entries), MANUAL_PATH.name)

    VALIDATED_PATH.write_text(
        yaml.safe_dump({"sources": ok_entries + manual_entries}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    total = len(ok_entries) + len(manual_entries)
    logger.info(
        "\nDone: %d source(s) ready to be monitored (%d auto-validated, %d manual). Saved to %s.",
        total,
        len(ok_entries),
        len(manual_entries),
        VALIDATED_PATH.name,
    )
    if len(ok_entries) < len(urls):
        logger.info(
            "Skipped URLs will NOT be monitored until you fix or remove them in "
            "sources.yaml and re-run this validation."
        )

    write_step_summary(results, len(manual_entries))


if __name__ == "__main__":
    main()

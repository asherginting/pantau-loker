import logging
import os

from dotenv import load_dotenv

from cv_loader import load_cv
from job import Job
from matcher import score_match
from notifier import send_telegram

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def check_resume() -> bool:
    try:
        text = load_cv()
    except Exception as exc:
        logger.error("Resume: FAILED (%s)", exc)
        return False
    logger.info("Resume: OK (%d characters loaded)", len(text))
    return True


def check_groq() -> bool:
    if not os.environ.get("GROQ_API_KEY"):
        logger.error("Groq API: FAILED (GROQ_API_KEY is not set)")
        return False

    sample_job = Job(
        id="test",
        source="test",
        title="Software Engineer",
        company="Test Co",
        location="Remote",
        description="A test job posting used only to verify the AI matching setup works.",
    )
    try:
        result = score_match("Experienced software engineer skilled in Python.", sample_job)
    except Exception as exc:
        logger.error("Groq API: FAILED (%s)", exc)
        return False
    logger.info("Groq API: OK (test match score: %s%%)", result["score"])
    return True


def check_telegram() -> bool:
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        logger.error("Telegram: FAILED (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID is not set)")
        return False

    try:
        send_telegram("✅ pantau-loker setup test: Telegram notifications are working.")
    except Exception as exc:
        logger.error("Telegram: FAILED (%s)", exc)
        return False
    logger.info("Telegram: OK (check your chat for the test message)")
    return True


def main() -> None:
    load_dotenv()
    logger.info("Checking pantau-loker setup...\n")

    results = {
        "Resume": check_resume(),
        "Groq API": check_groq(),
        "Telegram": check_telegram(),
    }

    logger.info("")
    if all(results.values()):
        logger.info("All checks passed. You're ready to enable the Monitor Jobs workflow.")
        return

    failed = [name for name, ok in results.items() if not ok]
    logger.error("Some checks failed: %s. Fix these before enabling monitoring.", ", ".join(failed))
    raise SystemExit(1)


if __name__ == "__main__":
    main()

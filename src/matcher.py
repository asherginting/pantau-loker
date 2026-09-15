import json
import os
import re
import time

from groq import Groq

from job import Job

_client_instance: Groq | None = None
RATE_LIMIT_RETRY_DELAY_SECONDS = 30
CV_CHAR_LIMIT = 3000
DESCRIPTION_CHAR_LIMIT = 1500


def _client() -> Groq:
    global _client_instance
    if _client_instance is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client_instance = Groq(api_key=api_key)
    return _client_instance


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            text = rest if first_line.lower().startswith("json") else text
    return json.loads(text)


def _extract_retry_delay(exc: Exception) -> float | None:
    match = re.search(r"retry.*?(\d+(?:\.\d+)?)\s*s", str(exc), re.IGNORECASE)
    return float(match.group(1)) if match else None


def _complete(client: Groq, model_name: str, prompt: str) -> tuple[str, int]:
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    tokens_used = response.usage.total_tokens if response.usage else 0
    return response.choices[0].message.content, tokens_used


def _generate_with_retry(client: Groq, model_name: str, prompt: str) -> tuple[str, int]:
    try:
        return _complete(client, model_name, prompt)
    except Exception as exc:
        if "429" not in str(exc) and "rate_limit" not in str(exc).lower():
            raise
        time.sleep(_extract_retry_delay(exc) or RATE_LIMIT_RETRY_DELAY_SECONDS)
        return _complete(client, model_name, prompt)


def score_match(cv_text: str, job: Job) -> dict:
    client = _client()
    model_name = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

    prompt = f"""You are a recruiting assistant helping a job seeker decide which
postings deserve their attention.

Give:
1. A match score from 0 to 100 based on how directly their skills and
   experience align with the role's stated requirements.
2. Whether this is still worth applying to even if the direct skill overlap
   isn't very high — for example, because the required skills are closely
   related to what the candidate already knows, the gap looks learnable on
   the job, or the core domain overlaps enough to make it a reasonable
   stretch. Be selective: only mark this true when there's a genuine,
   specific reason, not for every posting.

Reply with ONLY this JSON, no other text, no markdown:
{{"score": <integer 0-100>, "reason": "<one or two sentence explanation>", "worth_trying": <true or false>}}

=== RESUME ===
{cv_text[:CV_CHAR_LIMIT]}

=== JOB POSTING ===
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:DESCRIPTION_CHAR_LIMIT]}
"""

    text, tokens_used = _generate_with_retry(client, model_name, prompt)
    try:
        result = _parse_json_response(text)
        return {
            "score": int(result.get("score", 0)),
            "reason": result.get("reason", ""),
            "worth_trying": bool(result.get("worth_trying", False)),
            "tokens_used": tokens_used,
        }
    except (json.JSONDecodeError, ValueError, AttributeError):
        return {
            "score": 0,
            "reason": f"Failed to parse AI response: {text[:200]}",
            "worth_trying": False,
            "tokens_used": tokens_used,
        }

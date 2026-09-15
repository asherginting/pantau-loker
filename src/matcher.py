import json
import os
import re
import time

from google import genai

from job import Job

_client_instance: genai.Client | None = None
RATE_LIMIT_RETRY_DELAY_SECONDS = 30


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client_instance = genai.Client(api_key=api_key)
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
    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", str(exc))
    return float(match.group(1)) if match else None


def _generate_with_retry(client: genai.Client, model_name: str, prompt: str):
    try:
        return client.models.generate_content(model=model_name, contents=prompt)
    except Exception as exc:
        if "429" not in str(exc) and "RESOURCE_EXHAUSTED" not in str(exc):
            raise
        time.sleep(_extract_retry_delay(exc) or RATE_LIMIT_RETRY_DELAY_SECONDS)
        return client.models.generate_content(model=model_name, contents=prompt)


def score_match(cv_text: str, job: Job) -> dict:
    client = _client()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

    prompt = f"""You are a recruiting assistant. Compare the candidate's resume with the
job posting below, then give a match score from 0 to 100 based on how well their
skills, experience, and role fit align.

Reply with ONLY this JSON, no other text, no markdown:
{{"score": <integer 0-100>, "reason": "<one or two sentence explanation>"}}

=== RESUME ===
{cv_text}

=== JOB POSTING ===
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:4000]}
"""

    response = _generate_with_retry(client, model_name, prompt)
    try:
        result = _parse_json_response(response.text)
        return {"score": int(result.get("score", 0)), "reason": result.get("reason", "")}
    except (json.JSONDecodeError, ValueError, AttributeError):
        return {"score": 0, "reason": f"Failed to parse AI response: {response.text[:200]}"}

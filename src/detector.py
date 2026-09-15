import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from fetcher import extract_inline_json_blobs, fetch_from_source
from http_utils import USER_AGENT, is_allowed_by_robots, polite_get

COMMON_FEED_SUFFIXES = ["feed", "rss", "jobs/feed", "feed/"]
DYNAMIC_DISCOVERY_TIMEOUT_MS = 15000

TITLE_KEYS = {"title", "jobtitle", "position", "role", "name"}
LOCATION_KEYS = {"location", "city", "candidaterequiredlocation", "workplace", "office"}
URL_KEYS = {"url", "link", "applyurl", "joburl", "hostedurl", "absoluteurl"}
COMPANY_KEYS = {"company", "companyname", "employer", "organization", "clientname", "hiringcompany"}
ID_KEYS = {"id", "_id", "jobid", "uuid"}
DESCRIPTION_KEYS = {"description", "descriptionhtml", "descriptionplain", "content", "summary"}
DATE_KEYS = {"publishedat", "createdat", "date", "postedat", "updatedat", "publicationdate"}


def _try_jsonld(url: str) -> dict | None:
    if not is_allowed_by_robots(url):
        return {"status": "skip", "url": url, "reason": f"robots.txt disallows access to {url}"}

    entry = {"url": url, "method": "jsonld", "endpoint": url}
    try:
        jobs = fetch_from_source(entry)
    except Exception as exc:
        return {"status": "skip", "url": url, "reason": f"Page could not be fetched or parsed: {exc}"}

    if not jobs:
        return None
    return {"status": "ok", "url": url, "entry": entry, "sample_count": len(jobs)}


def _discover_feed_url(url: str) -> str | None:
    try:
        response = polite_get(url)
        response.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    link = soup.find("link", rel="alternate", type=lambda t: t and "rss" in t)
    if link and link.get("href"):
        return urljoin(url, link["href"])

    base = url if url.endswith("/") else url + "/"
    for suffix in COMMON_FEED_SUFFIXES:
        candidate = urljoin(base, suffix)
        try:
            probe = polite_get(candidate)
        except Exception:
            continue
        if probe.ok and "<rss" in probe.text[:1000].lower():
            return candidate

    return None


def _try_rss(url: str) -> dict | None:
    feed_url = _discover_feed_url(url)
    if not feed_url:
        return None

    if not is_allowed_by_robots(feed_url):
        return {"status": "skip", "url": url, "reason": f"robots.txt disallows access to {feed_url}"}

    entry = {"url": url, "method": "rss", "endpoint": feed_url}
    try:
        jobs = fetch_from_source(entry)
    except Exception as exc:
        return {"status": "skip", "url": url, "reason": f"Found RSS feed ({feed_url}) but failed to fetch it: {exc}"}

    if not jobs:
        return {"status": "skip", "url": url, "reason": f"RSS feed {feed_url} found but contains no entries"}
    return {"status": "ok", "url": url, "entry": entry, "sample_count": len(jobs)}


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


SUPPORTING_KEYS = LOCATION_KEYS | URL_KEYS | COMPANY_KEYS | DESCRIPTION_KEYS


def _looks_like_job_shape(sample: dict) -> bool:
    keys = {_normalize_key(k) for k in sample.keys()}
    has_title = bool(keys & TITLE_KEYS)
    has_supporting_signal = bool(keys & SUPPORTING_KEYS)
    return has_title and has_supporting_signal


MAX_SEARCH_DEPTH = 5


def _find_job_list(data) -> tuple[list[str], list[dict]] | None:
    def walk(node, path: list[str], depth: int):
        if depth > MAX_SEARCH_DEPTH:
            return None
        if isinstance(node, list) and node and isinstance(node[0], dict):
            if _looks_like_job_shape(node[0]):
                return path, node
        if isinstance(node, dict):
            for key, value in node.items():
                found = walk(value, path + [key], depth + 1)
                if found:
                    return found
        return None

    return walk(data, [], 0)


def _detect_field_map(sample: dict) -> dict[str, str | None]:
    normalized = {_normalize_key(k): k for k in sample.keys()}

    def pick(options: set[str]) -> str | None:
        for option in options:
            if option in normalized:
                return normalized[option]
        return None

    return {
        "id": pick(ID_KEYS),
        "title": pick(TITLE_KEYS),
        "company": pick(COMPANY_KEYS),
        "location": pick(LOCATION_KEYS),
        "url": pick(URL_KEYS),
        "description": pick(DESCRIPTION_KEYS),
        "published_at": pick(DATE_KEYS),
    }


def _try_embedded(url: str) -> dict | None:
    if not is_allowed_by_robots(url):
        return {"status": "skip", "url": url, "reason": f"robots.txt disallows access to {url}"}

    try:
        response = polite_get(url)
        response.raise_for_status()
    except Exception:
        return None

    for blob in extract_inline_json_blobs(response.text):
        found = _find_job_list(blob)
        if not found:
            continue
        list_path, items = found
        entry = {
            "url": url,
            "method": "embedded",
            "endpoint": url,
            "list_path": list_path,
            "fields": _detect_field_map(items[0]),
        }
        try:
            jobs = fetch_from_source(entry)
        except Exception:
            continue
        if jobs:
            return {"status": "ok", "url": url, "entry": entry, "sample_count": len(jobs)}

    return None


def _discover_dynamic_source(url: str) -> dict | None:
    candidates = []

    def handle_response(response) -> None:
        if "json" not in response.headers.get("content-type", ""):
            return
        try:
            data = response.json()
        except Exception:
            return
        found = _find_job_list(data)
        if not found:
            return
        list_path, items = found
        request = response.request
        candidates.append(
            {
                "endpoint": response.url,
                "http_method": request.method,
                "post_data": request.post_data,
                "list_path": list_path,
                "items": items,
            }
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(user_agent=USER_AGENT)
            page.on("response", handle_response)
            try:
                page.goto(url, timeout=DYNAMIC_DISCOVERY_TIMEOUT_MS, wait_until="networkidle")
            except Exception:
                pass
            browser.close()
    except Exception:
        return None

    if not candidates:
        return None
    return max(candidates, key=lambda c: len(c["items"]))


def _try_dynamic(url: str) -> dict | None:
    discovered = _discover_dynamic_source(url)
    if not discovered:
        return None

    endpoint = discovered["endpoint"]
    if not is_allowed_by_robots(endpoint):
        return {
            "status": "skip",
            "url": url,
            "reason": f"Found a live API call to {endpoint} but robots.txt disallows it",
        }

    entry = {
        "url": url,
        "method": "dynamic",
        "endpoint": endpoint,
        "http_method": discovered["http_method"],
        "post_data": discovered["post_data"],
        "list_path": discovered["list_path"],
        "fields": _detect_field_map(discovered["items"][0]),
    }

    try:
        jobs = fetch_from_source(entry)
    except Exception as exc:
        return {
            "status": "skip",
            "url": url,
            "reason": f"Found endpoint ({endpoint}) but a follow-up fetch failed: {exc}",
        }

    if not jobs:
        return None
    return {"status": "ok", "url": url, "entry": entry, "sample_count": len(jobs)}


def validate_source(url: str) -> dict:
    url = url.strip()
    if not re.match(r"^https?://", url):
        return {
            "status": "skip",
            "url": url,
            "reason": "Not a valid URL (must start with http:// or https://)",
        }

    for strategy in (_try_jsonld, _try_rss, _try_embedded, _try_dynamic):
        result = strategy(url)
        if result is not None:
            return result

    return {
        "status": "skip",
        "url": url,
        "reason": (
            "No safe, verifiable job data source found (no JobPosting schema, no RSS "
            "feed, no job data embedded in the page, and no job-shaped API call "
            "observed while loading the page)."
        ),
    }

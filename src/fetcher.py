import hashlib
import json

import feedparser
from bs4 import BeautifulSoup

from http_utils import extract_path, polite_get, polite_post_json
from job import Job


def _hash_id(*parts: str) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _extract_jsonld_jobpostings(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    postings = []

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, dict) and "@graph" in data:
            candidates = data["@graph"]
        elif isinstance(data, list):
            candidates = data
        else:
            candidates = [data]

        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" in types:
                postings.append(item)

    return postings


def _job_from_jsonld(item: dict, page_url: str) -> Job:
    org = item.get("hiringOrganization")
    org_name = org.get("name", "") if isinstance(org, dict) else ""

    location = item.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else {}

    location_str = ""
    if isinstance(location, dict):
        address = location.get("address") or {}
        if isinstance(address, dict):
            location_str = ", ".join(
                filter(
                    None,
                    [
                        address.get("addressLocality"),
                        address.get("addressRegion"),
                        address.get("addressCountry"),
                    ],
                )
            )

    url = item.get("url") or page_url
    job_id = item.get("identifier")
    if isinstance(job_id, dict):
        job_id = job_id.get("value")
    if not job_id:
        job_id = _hash_id(url, item.get("title", ""))

    return Job(
        id=f"jsonld:{job_id}",
        source="jsonld",
        title=item.get("title", ""),
        company=org_name,
        location=location_str,
        url=url,
        description=str(item.get("description", ""))[:6000],
        published_at=item.get("datePosted"),
    )


def _fetch_rss(entry: dict) -> list[Job]:
    response = polite_get(entry["endpoint"])
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    jobs = []
    for item in feed.entries:
        guid = item.get("id") or item.get("link", "")
        jobs.append(
            Job(
                id=f"rss:{_hash_id(guid)}",
                source="rss",
                title=item.get("title", ""),
                url=item.get("link", ""),
                description=item.get("summary", ""),
                published_at=item.get("published"),
            )
        )
    return jobs


def _fetch_jsonld(entry: dict) -> list[Job]:
    response = polite_get(entry["endpoint"])
    response.raise_for_status()
    postings = _extract_jsonld_jobpostings(response.text)
    return [_job_from_jsonld(posting, entry["endpoint"]) for posting in postings]


NESTED_NAME_KEYS = ("name", "title", "label", "displayName", "formattedName")


def _field(item: dict, fields: dict, name: str) -> str:
    key = fields.get(name)
    if not key:
        return ""
    value = item.get(key)
    if isinstance(value, dict):
        for nested_key in NESTED_NAME_KEYS:
            if isinstance(value.get(nested_key), str):
                return value[nested_key]
        return ""
    if isinstance(value, list):
        return ""
    return str(value) if value is not None else ""


def _jobs_from_items(items: list, fields: dict, source: str) -> list[Job]:
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue

        title = _field(item, fields, "title")
        url = _field(item, fields, "url")
        id_key = fields.get("id")
        raw_id = item.get(id_key) if id_key else None
        job_id = raw_id or _hash_id(url, title)

        jobs.append(
            Job(
                id=f"{source}:{job_id}",
                source=source,
                title=title,
                company=_field(item, fields, "company"),
                location=_field(item, fields, "location"),
                url=url,
                description=_field(item, fields, "description")[:6000],
                published_at=_field(item, fields, "published_at") or None,
            )
        )
    return jobs


def _fetch_dynamic(entry: dict) -> list[Job]:
    if entry.get("http_method") == "POST":
        body = json.loads(entry["post_data"]) if entry.get("post_data") else {}
        response = polite_post_json(entry["endpoint"], json_body=body)
    else:
        response = polite_get(entry["endpoint"])
    response.raise_for_status()
    data = response.json()

    items = extract_path(data, entry.get("list_path") or [])
    if not isinstance(items, list):
        items = []
    return _jobs_from_items(items, entry.get("fields", {}), "dynamic")


def extract_inline_json_blobs(html_text: str) -> list:
    blobs = []
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup.find_all("script"):
        if tag.get("type") == "application/ld+json":
            continue
        text = tag.string
        if not text or len(text) < 200:
            continue

        decoder = json.JSONDecoder()
        idx = text.find("{")
        while idx != -1:
            try:
                obj, _ = decoder.raw_decode(text, idx)
                blobs.append(obj)
                break
            except json.JSONDecodeError:
                idx = text.find("{", idx + 1)

    return blobs


def _fetch_embedded(entry: dict) -> list[Job]:
    response = polite_get(entry["endpoint"])
    response.raise_for_status()

    for blob in extract_inline_json_blobs(response.text):
        items = extract_path(blob, entry.get("list_path") or [])
        if isinstance(items, list):
            return _jobs_from_items(items, entry.get("fields", {}), "embedded")

    return []


def fetch_from_source(entry: dict) -> list[Job]:
    method = entry.get("method")
    if method == "rss":
        return _fetch_rss(entry)
    if method == "jsonld":
        return _fetch_jsonld(entry)
    if method == "embedded":
        return _fetch_embedded(entry)
    if method == "dynamic":
        return _fetch_dynamic(entry)
    raise ValueError(f"Unknown source method: {method}")

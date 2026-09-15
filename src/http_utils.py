import urllib.robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = "pantau-loker/1.0 (+https://github.com/asherginting/pantau-loker)"
DEFAULT_TIMEOUT = 20

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def polite_get(url: str, **kwargs) -> requests.Response:
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("User-Agent", USER_AGENT)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return requests.get(url, headers=headers, **kwargs)


def polite_post_json(
    url: str, headers: dict | None = None, json_body: dict | None = None
) -> requests.Response:
    headers = dict(headers or {})
    headers.setdefault("User-Agent", USER_AGENT)
    headers.setdefault("Content-Type", "application/json")
    return requests.post(url, headers=headers, json=json_body or {}, timeout=DEFAULT_TIMEOUT)


def extract_path(data, path: list[str]):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _fetch_robots(origin: str) -> urllib.robotparser.RobotFileParser | None:
    try:
        response = polite_get(f"{origin}/robots.txt")
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


def is_allowed_by_robots(url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        _robots_cache[origin] = _fetch_robots(origin)

    parser = _robots_cache[origin]
    if parser is None:
        return True
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "sources.yaml"
CONFIG_PATH = ROOT / "config.yaml"

DEFAULT_MAX_SOURCES = 50
URL_PATTERN = re.compile(r"^https?://\S+$")


def parse_input(raw: str) -> list[str]:
    parts = re.split(r"[,\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def split_valid(urls: list[str]) -> tuple[list[str], list[str]]:
    valid = [u for u in urls if URL_PATTERN.match(u)]
    invalid = [u for u in urls if not URL_PATTERN.match(u)]
    return valid, invalid


def load_max_sources() -> int:
    if not CONFIG_PATH.exists():
        return DEFAULT_MAX_SOURCES
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return (config.get("validation", {}) or {}).get("max_sources", DEFAULT_MAX_SOURCES)


def add_urls(new_urls: list[str], max_sources: int) -> tuple[list[str], int]:
    text = SOURCES_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    existing = [str(u).strip() for u in (data.get("urls") or [])]

    candidates = [url for url in new_urls if url not in existing]
    room = max(max_sources - len(existing), 0)
    added = candidates[:room]
    dropped = len(candidates) - len(added)

    if not added:
        return [], dropped

    combined = existing + added
    lines = text.splitlines()
    new_lines = []
    inserted = False

    for line in lines:
        if line.strip() == "urls: []":
            new_lines.append("urls:")
            new_lines.extend(f"  - {url}" for url in combined)
            inserted = True
            continue
        new_lines.append(line)

    if not inserted:
        for index, line in enumerate(new_lines):
            if line.strip() == "urls:":
                insert_at = index + 1
                while insert_at < len(new_lines) and new_lines[insert_at].strip().startswith("-"):
                    insert_at += 1
                for offset, url in enumerate(added):
                    new_lines.insert(insert_at + offset, f"  - {url}")
                inserted = True
                break

    if not inserted:
        new_lines.append("urls:")
        new_lines.extend(f"  - {url}" for url in combined)

    SOURCES_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return added, dropped


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    parsed = parse_input(raw)
    if not parsed:
        print("No URLs provided.")
        return

    urls, invalid = split_valid(parsed)
    if invalid:
        print(f"Ignored {len(invalid)} entr(ies) that aren't a plain http(s) URL:")
        for entry in invalid:
            print(f"  - {entry!r}")
        print()

    if not urls:
        print("No valid URLs to add.")
        return

    max_sources = load_max_sources()
    added, dropped = add_urls(urls, max_sources)

    if added:
        print(f"Added {len(added)} new URL(s):")
        for url in added:
            print(f"  - {url}")
    else:
        print("No new URLs added (already present, or the limit below was already reached).")

    if dropped:
        print(
            f"\n{dropped} URL(s) were NOT added: sources.yaml is capped at {max_sources} "
            "entries (config.yaml -> validation.max_sources), to keep validation runs "
            "fast and avoid accidental or careless mass submissions. Remove some "
            "existing URLs first if you need room for more."
        )


if __name__ == "__main__":
    main()

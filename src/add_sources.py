import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "sources.yaml"


def parse_input(raw: str) -> list[str]:
    parts = re.split(r"[,\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def add_urls(new_urls: list[str]) -> list[str]:
    text = SOURCES_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    existing = [str(u).strip() for u in (data.get("urls") or [])]

    added = [url for url in new_urls if url not in existing]
    if not added:
        return []

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
    return added


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    urls = parse_input(raw)
    if not urls:
        print("No URLs provided.")
        return

    added = add_urls(urls)
    if added:
        print(f"Added {len(added)} new URL(s):")
        for url in added:
            print(f"  - {url}")
    else:
        print("No new URLs to add (already present).")


if __name__ == "__main__":
    main()

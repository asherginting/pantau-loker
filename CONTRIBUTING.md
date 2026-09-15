# Contributing to pantau-loker

Thanks for considering a contribution. This project is intentionally small
and generic — no company or platform is ever hardcoded — so most useful
contributions fall into a few categories below.

## Before you start

For anything more than a small fix, please open an issue first to discuss
the change. This avoids wasted effort on a pull request that doesn't fit the
project's direction.

## Reporting bugs

Open an issue using the **Bug report** template. Include:

- What you expected to happen vs. what actually happened
- The relevant log output (from a GitHub Actions run, or your terminal)
- Whether it happens with a specific source URL

Never paste real secrets (tokens, API keys) into an issue.

## Suggesting a source-detection improvement

`src/detector.py` deliberately only accepts sources that expose public,
machine-readable data (`JobPosting` schema.org markup, RSS, embedded JSON, or
a live API call the page's own frontend makes). If you've found a site that
should be detectable but isn't, open an issue with the URL and what you
found — a PR is even better.

Contributions that add scraping of rendered HTML, or that guess at
undocumented API endpoints, will not be accepted — see [Security
notes](README.md#security-notes) for why.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in your own test credentials
```

Before opening a PR, make sure your change at least compiles and lints
cleanly:

```bash
python -m py_compile src/*.py
python -m pip install pyflakes && python -m pyflakes src/*.py
```

## Code style

- No comments explaining *what* code does — names should make that clear.
  A short comment is fine only for a genuinely non-obvious *why*.
- Keep functions small and single-purpose, matching the existing style in
  `src/`.
- Don't add a dependency, abstraction, or configuration option for a
  hypothetical future need — only for what the change actually requires.

## Pull requests

- Keep PRs focused on one change.
- Explain what you tested and how (especially for anything touching
  `detector.py` or `fetcher.py` — a live URL you validated against is the
  most convincing evidence).
- By contributing, you agree your contribution is licensed under this
  project's [MIT License](LICENSE).

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By
participating, you're expected to uphold it.

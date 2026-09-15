# Changelog

All notable changes to this project are documented in this file. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, issue and pull
  request templates, to complete GitHub's community standards checklist.
- "Project status" and "Troubleshooting" sections in the README.

## [0.1.0] — initial version

### Added

- Generic, four-strategy source detection (`JobPosting` schema.org, RSS,
  embedded page JSON, and live API observation via a headless browser) —
  no company or platform is ever hardcoded.
- `sources.manual.yaml` as an explicit, user-controlled escape hatch for
  sources that pass every safety check manually but can't be auto-detected.
- AI-based resume matching, with a configurable score threshold.
- Telegram notifications for matches above the threshold.
- `Validate Sources`, `Monitor Jobs`, and `Test Setup` GitHub Actions
  workflows, including adding new URLs directly from a workflow input box.
- Round-robin job interleaving across sources, so one large source can't
  consume the whole run's AI budget before smaller sources are ever checked.
- `robots.txt` enforcement, bounded request timeouts, per-workflow
  `timeout-minutes`, and a hard cap on `sources.yaml` size, to keep the tool
  from being turned into a way to hammer third-party servers.

### Changed

- Switched AI matching from Gemini to Groq after finding Gemini's free-tier
  daily quota (as low as 20 requests/day for some models) impractical for
  this use case; Groq's free tier allows far more headroom for the same
  workload.

### Fixed

- Jobs with no application link (e.g., non-job blog content picked up by a
  noisy RSS feed) are now filtered out before AI scoring, instead of
  occasionally being scored and even notified with blank fields.
- The Telegram bot token is no longer included in error messages when a
  Telegram request fails.
- RSS fetching now goes through a bounded-timeout request instead of a
  direct, unbounded fetch, so a slow feed can't hang a run.

# Security Policy

## Reporting a Vulnerability

If you find a security vulnerability in pantau-loker, please report it
privately rather than opening a public issue:

1. Go to the [Security tab](../../security) of this repository.
2. Click **Report a vulnerability** to open a private advisory.

If that option isn't available on this fork, open a regular issue with a
minimal description and **no exploit details**, and ask the maintainer to
follow up privately.

Please include:

- What kind of issue it is (e.g., secret leakage, a way to bypass
  `robots.txt` checks, a denial-of-service vector)
- Steps to reproduce
- The potential impact

## Scope

This project runs entirely inside your own fork's GitHub Actions and your
own accounts (Telegram, Groq). Reports are especially welcome for:

- Any way a workflow input or a job source's data could lead to command or
  YAML injection
- Any way a secret (Telegram token, Groq API key, resume URL) could leak
  into logs, commit history, or a notification
- Any way the tool could be made to poll a site in a way that ignores
  `robots.txt` or hammers a server beyond the configured limits

## Response

This is a community-maintained open source project without a dedicated
security team. Reports will be acknowledged and addressed on a best-effort
basis.

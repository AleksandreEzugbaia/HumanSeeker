# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in HumanSeeker, please report it responsibly. **Do not open a public GitHub issue** for security vulnerabilities.

Instead:

1. Open a private security advisory at [github.com/AleksandreEzugbaia/HumanSeeker/security/advisories](https://github.com/AleksandreEzugbaia/HumanSeeker/security/advisories)
2. Or contact the maintainer directly via the email listed on the GitHub profile.

When reporting, please include:

- A clear description of the vulnerability and its impact.
- Steps to reproduce, including any relevant payloads or configurations.
- The version of HumanSeeker affected.
- Any suggested mitigation, if you have one.

## Response Expectations

- **Acknowledgment:** within 72 hours of receiving the report.
- **Initial assessment:** within 7 days.
- **Patch release** for confirmed vulnerabilities: within 30 days for high-severity issues, 90 days for medium- and low-severity issues.
- **Public disclosure:** coordinated with the reporter after a fix is available.

## Scope

In scope:

- The Flask backend and its API endpoints
- The browser-side telemetry tracker (`frontend/tracker.js`)
- Input validation, rate limiting, and security headers
- Detection event logging integrity

Out of scope:

- Issues that require physical access to the host OS
- Vulnerabilities in third-party dependencies (please report these upstream; we'll bump the dependency version once patched)
- Social engineering of the project maintainer

## Hardening Notes for Operators

If you deploy HumanSeeker in any setting beyond a personal workstation:

- Run the app under a dedicated, low-privilege user account.
- Restrict the local data directory (`baselines/`, `logs/`) to that user account only.
- Do not expose the Flask server beyond 127.0.0.1. The app is loopback-only by design; do not bind it to a public interface.
- Periodically rotate or archive `logs/detections.jsonl` to limit data retention.
- Treat detection events as PII-adjacent: behavioral signatures can identify individuals.

## Coordinated Disclosure

We follow a 90-day coordinated disclosure timeline by default, extendable by mutual agreement if a fix requires deeper coordination. Credit to security researchers is provided in `CHANGELOG.md` and the associated GitHub Security Advisory unless anonymity is requested.

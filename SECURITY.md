# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Toolforge, please report it responsibly.

**Do not** open a public GitHub issue for security vulnerabilities.

Instead:

1. Email the maintainers (or open a private security advisory on GitHub if available).
2. Include a clear description of the issue, steps to reproduce, and potential impact.
3. Allow reasonable time for a fix before any public disclosure.

We will acknowledge receipt within 72 hours and aim to provide a timeline for a fix.

## Scope

Toolforge is a local-first developer tool. It does not process user data in the cloud by default. The main security considerations are:

- Handling of optional API keys (e.g. `ANTHROPIC_API_KEY`)
- Execution of user-supplied or agent-generated tool schemas
- Future code-mode / sandbox execution paths

Please report any issues related to these areas.

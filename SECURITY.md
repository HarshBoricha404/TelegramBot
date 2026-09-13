# Security Policy

## Supported version

Security fixes are applied to the latest code on the `main` branch.

## Reporting a vulnerability

Do not open a public issue containing a Telegram token, private channel ID, personal data, or instructions that could expose another user's deployment.

Use GitHub's **Report a vulnerability** option under the repository's Security tab. If private vulnerability reporting is unavailable, open a public issue containing no sensitive details and ask the maintainer for a private contact method.

Include:

- the affected file or workflow;
- the impact;
- safe reproduction steps with fake credentials;
- a suggested fix, if available.

## Credential exposure

If a Telegram bot token is exposed:

1. Revoke and regenerate it immediately with [@BotFather](https://t.me/BotFather).
2. Replace the GitHub environment secret.
3. Remove the token from files and Git history where practical.
4. Review Telegram and GitHub Actions activity for unexpected use.

Do not rely on deleting only the latest commit: credentials can remain in Git history and caches.

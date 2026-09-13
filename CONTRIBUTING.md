# Contributing

Thanks for helping improve the IPO Signal Telegram Bot.

## Development setup

```bash
git clone https://github.com/YOUR_USERNAME/TelegramBot.git
cd TelegramBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

The test suite is offline. HTML source fragments belong in `tests/fixtures/`; keep fixtures small and remove unrelated scripts, tracking data, credentials, and personal information.

## Pull requests

Keep each pull request focused and explain:

- what changed;
- why the change improves reliability or user experience;
- which public data source supports a scoring change;
- how failure, missing data, and changed HTML layouts are handled;
- which tests cover the change.

Before opening a pull request:

```bash
pytest -q
```

Never commit `.env`, Telegram tokens, real private channel IDs, API keys, or copied credentials. Pull requests do not receive deployment secrets.

## Parser changes

- Parse by normalized table headings and labels, not fixed column positions.
- Add a compact HTML fixture for every supported layout.
- Fail closed when identity, freshness, dates, or required fields cannot be verified.
- Keep network requests out of tests.
- Respect source availability and avoid adding browser automation or paid services without prior discussion.

## Scoring changes

Scoring must remain deterministic and explainable.

- Add tests for both the positive signal and its counterexample.
- Document thresholds and evidence in the pull request.
- Do not present the score as a probability or guaranteed return.
- Prefer conservative penalties and eligibility gates when data is stale, disputed, or missing.
- Avoid tailoring recommendations to an individual investor.

## Reporting bugs and security issues

Use a GitHub issue for ordinary parser or scoring bugs. For credentials, private data, or another security-sensitive report, follow [SECURITY.md](SECURITY.md) and do not post the details publicly.

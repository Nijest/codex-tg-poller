# codex-tg-poller

Reads task messages from a Telegram bot and hands them to a private runner repo,
which executes them with Codex and answers back in Telegram.

**Why this repo is public:** Actions minutes are unlimited on public repos. A
5-minute cron would otherwise eat the entire free tier of a private repo, where
every run is billed as a full minute even when there is nothing to do.

Nothing secret lives here. Tokens come from Actions secrets, Codex never runs in
this repo, and the poller prints only counters — never message text, because
logs here are world-readable. `tests/test_poller.py` pins that property.

## Secrets

| name | what |
|---|---|
| `NOTIFY_BOT_TOKEN` | Telegram bot token |
| `NOTIFY_CHAT_ID` | the only chat allowed to spend runner minutes |
| `RUNNER_REPO` | `owner/name` of the private runner |
| `RUNNER_DISPATCH_TOKEN` | fine-grained PAT, Contents: write on the runner repo |

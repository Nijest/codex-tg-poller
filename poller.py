#!/usr/bin/env python3
"""Poll Telegram for task messages and hand them to the private runner repo.

Runs from a public repo, so it must never print message text: job logs are
public. Only counts and update ids go to stdout.

Stateless by design. Telegram acks updates when getUpdates is called with
offset = last_id + 1, so a failed run simply leaves them for the next one.
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"
DISPATCH = "https://api.github.com/repos/{repo}/dispatches"


def telegram(token, method, **params):
    url = API.format(token=token, method=method)
    data = json.dumps(params).encode() if params else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if not payload.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {payload.get('description')}")
    return payload["result"]


def dispatch(repo, token, prompt, update_id):
    body = json.dumps(
        {
            "event_type": "codex-task",
            "client_payload": {"prompt": prompt, "update_id": update_id},
        }
    ).encode()
    req = urllib.request.Request(
        DISPATCH.format(repo=repo),
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status not in (204, 200):
            raise RuntimeError(f"dispatch returned HTTP {resp.status}")


def main():
    # Actions hands a missing secret over as an empty string, not as an unset
    # variable, so an unconfigured repo would quietly 401 instead of saying why
    missing = [
        name
        for name in (
            "NOTIFY_BOT_TOKEN",
            "NOTIFY_CHAT_ID",
            "RUNNER_REPO",
            "RUNNER_DISPATCH_TOKEN",
        )
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError(f"secrets not set: {', '.join(missing)}")

    bot_token = os.environ["NOTIFY_BOT_TOKEN"]
    owner_chat = str(os.environ["NOTIFY_CHAT_ID"]).strip()
    runner_repo = os.environ["RUNNER_REPO"].strip()
    gh_token = os.environ["RUNNER_DISPATCH_TOKEN"]

    updates = telegram(bot_token, "getUpdates", timeout=0, allowed_updates=["message"])
    if not updates:
        print("no updates")
        return 0

    accepted = ignored = 0
    done_through = None

    try:
        for u in sorted(updates, key=lambda x: x["update_id"]):
            message = u.get("message") or {}
            text = (message.get("text") or "").strip()
            chat_id = str((message.get("chat") or {}).get("id", ""))

            # anyone can message a bot; only the owner may spend Codex minutes
            if chat_id != owner_chat or not text:
                ignored += 1
            else:
                dispatch(runner_repo, gh_token, text, u["update_id"])
                accepted += 1
            done_through = u["update_id"]
    finally:
        # ack only what we finished, so a mid-loop failure re-sends just the
        # update that broke and never re-runs tasks already dispatched
        if done_through is not None:
            telegram(bot_token, "getUpdates", offset=done_through + 1, timeout=0)
            print(f"accepted={accepted} ignored={ignored} through {done_through}")
        else:
            print("nothing acked")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, RuntimeError, KeyError) as exc:
        # never interpolate message text into the error path
        print(f"poller failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

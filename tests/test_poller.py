#!/usr/bin/env python3
"""Checks for poller.py: chat filtering, ack point, and log hygiene.

Runs under pytest, or standalone with `python3 tests/test_poller.py` so the
workflow does not need pytest installed.
"""

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("NOTIFY_BOT_TOKEN", "t")
os.environ.setdefault("NOTIFY_CHAT_ID", "548958029")
os.environ.setdefault("RUNNER_REPO", "Nijest/codex-runner")
os.environ.setdefault("RUNNER_DISPATCH_TOKEN", "g")

OWNER = 548958029

spec = importlib.util.spec_from_file_location(
    "poller", str(Path(__file__).resolve().parent.parent / "poller.py")
)
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)


def msg(uid, chat, text):
    return {"update_id": uid, "message": {"text": text, "chat": {"id": chat}}}


def run(updates, dispatch_fails_on=None, telegram_fails=False):
    """Drive main() against fake transports. Returns (dispatched, acked, output)."""
    sent, acked = [], []

    def fake_telegram(token, method, **params):
        if "offset" in params:
            if telegram_fails:
                raise RuntimeError("telegram down")
            acked.append(params["offset"])
            return []
        return updates

    def fake_dispatch(repo, token, prompt, uid):
        if uid == dispatch_fails_on:
            raise RuntimeError("dispatch refused")
        sent.append((uid, prompt))

    poller.telegram, poller.dispatch = fake_telegram, fake_dispatch
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            poller.main()
        except RuntimeError:
            pass
    return sent, acked, buf.getvalue()


def test_only_owner_chat_is_executed():
    sent, acked, _ = run([msg(1, 999, "hack"), msg(2, OWNER, "fix bug")])
    assert sent == [(2, "fix bug")]
    assert acked == [3], "ack must cover the ignored update too"


def test_blank_text_is_ignored_but_acked():
    sent, acked, _ = run([msg(5, OWNER, "   ")])
    assert sent == []
    assert acked == [6]


def test_failed_dispatch_is_not_acked():
    sent, acked, _ = run(
        [msg(10, OWNER, "a"), msg(11, OWNER, "b"), msg(12, OWNER, "c")],
        dispatch_fails_on=11,
    )
    assert sent == [(10, "a")], "work after the failure must not be dispatched"
    assert acked == [11], "the broken update must come back next run"


def test_empty_batch_acks_nothing():
    _, acked, _ = run([])
    assert acked == []


def test_message_text_never_reaches_the_logs():
    """This repo is public, so its job logs are world-readable."""
    secret = "KLIENTSKIY-PAROL-42"
    _, _, output = run([msg(20, OWNER, secret), msg(21, 777, secret)])
    assert secret not in output


def test_message_text_never_leaks_through_an_error():
    secret = "KLIENTSKIY-PAROL-43"
    _, _, output = run([msg(30, OWNER, secret)], dispatch_fails_on=30)
    assert secret not in output

    _, _, output = run([msg(31, OWNER, secret)], telegram_fails=True)
    assert secret not in output


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"ok    {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\nпровалов: {failed}")
    sys.exit(1 if failed else 0)

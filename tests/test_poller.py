#!/usr/bin/env python3
"""Offline checks for poller.py: filtering, ack point, failure behaviour."""

import contextlib
import importlib.util
import io
from pathlib import Path
import os
import sys

os.environ.update(
    NOTIFY_BOT_TOKEN="t",
    NOTIFY_CHAT_ID="548958029",
    RUNNER_REPO="Nijest/codex-runner",
    RUNNER_DISPATCH_TOKEN="g",
)

spec = importlib.util.spec_from_file_location(
    "poller", str(Path(__file__).resolve().parent.parent / "poller.py")
)
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)


def msg(uid, chat, text):
    return {"update_id": uid, "message": {"text": text, "chat": {"id": chat}}}


def run(updates, dispatch_fails_on=None):
    sent, acked = [], []

    def fake_telegram(token, method, **p):
        if "offset" in p:
            acked.append(p["offset"])
            return []
        return updates

    def fake_dispatch(repo, token, prompt, uid):
        if uid == dispatch_fails_on:
            raise RuntimeError("boom")
        sent.append((uid, prompt))

    poller.telegram, poller.dispatch = fake_telegram, fake_dispatch
    try:
        poller.main()
    except RuntimeError:
        pass
    return sent, acked


fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(
        f"{'ok  ' if ok else 'FAIL'} {label}: {got!r}" + ("" if ok else f" != {want!r}")
    )


# 1. чужой чат отбрасывается, свой проходит
sent, acked = run([msg(1, 999, "hack"), msg(2, 548958029, "fix bug")])
check("только свой чат исполняется", sent, [(2, "fix bug")])
check("подтверждено по последний", acked, [3])

# 2. пустой текст игнорируется, но подтверждается
sent, acked = run([msg(5, 548958029, "   ")])
check("пустое не исполняется", sent, [])
check("пустое всё равно подтверждено", acked, [6])

# 3. падение на середине: подтверждаем только по успешные
sent, acked = run(
    [msg(10, 548958029, "a"), msg(11, 548958029, "b"), msg(12, 548958029, "c")],
    dispatch_fails_on=11,
)
check("до сбоя отправлено", sent, [(10, "a")])
check("подтверждено по 10, сбойное вернётся", acked, [11])

# 4. пустой список — ничего не подтверждаем
sent, acked = run([])
check("пусто — ack не шлём", acked, [])

# 5. главное свойство этого репо: логи публичные, текст задач туда попасть не должен
SECRET = "KLIENTSKIY-PAROL-42"
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
    run([msg(20, 548958029, SECRET), msg(21, 777, SECRET)])
check("текст сообщения не утёк в вывод", SECRET in buf.getvalue(), False)

print("\nПРОВАЛОВ:", fails)
sys.exit(1 if fails else 0)

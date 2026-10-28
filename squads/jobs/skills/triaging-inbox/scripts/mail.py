#!/usr/bin/env python3
"""Read-only job mail over IMAP for jobs-inbox: the password lives in the macOS Keychain, never in a file or a chat.

  mail.py setup [--email you@gmail.com]           two macOS dialogs: the address, then a Google app password
  mail.py status [--json]                         configured? and does the login work?
  mail.py search (--since YYYY-MM-DD | --minutes N) [--from DOMAIN ...] [--text WORD ...] [--limit 50] [--json]
  mail.py read UID [--json]

The account (address, host, port) is `$HERMES_HOME/mail.json`; the app password is the Keychain item
`hermes-jobs-inbox-imap` for that address. setup opens Google's app-password page in the user's own browser, asks for
the password in a hidden dialog, proves the login and only then stores it. Nothing here can send, move, flag, delete or
mark mail: the mailbox is opened with EXAMINE (read-only) and bodies are fetched with BODY.PEEK, so read state is kept.

search covers all mail (the `\\All` folder, so archived replies count) except what the account itself sent, and prints
uid, date, sender domain and subject, newest first; never a sender's name or address. read prints one message's text.

Exit 0 ok, 1 nothing found / not configured, 2 usage error, 3 login or server failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email
import email.policy
import email.utils
import imaplib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

SERVICE = "hermes-jobs-inbox-imap"
APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"
EMAIL_RE = re.compile(r"^[^@\s\"'\\]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$")
APP_PW_RE = re.compile(r"^[a-z]{16}$")
BODY_LIMIT = 20000


class Fail(Exception):
    def __init__(self, msg: str, code: int = 3):
        super().__init__(msg)
        self.code = code


def config_path() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "mail.json"


def load_config() -> dict:
    path = config_path()
    if not path.is_file():
        raise Fail("mail is not connected: ask the builder to connect jobs-inbox mail", 1)
    return json.loads(path.read_text())


def security(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    exe = shutil.which("security")
    if not exe:
        raise Fail("the macOS `security` tool is missing: the Keychain is macOS only")
    return subprocess.run([exe, *args], input=stdin, capture_output=True, text=True, timeout=30)


def keychain_password(address: str) -> str:
    done = security("find-generic-password", "-s", SERVICE, "-a", address, "-w")
    if done.returncode != 0:
        raise Fail(f"no app password in the Keychain for {address}: ask the builder to connect jobs-inbox mail", 1)
    return done.stdout.strip()


def keychain_store(address: str, password: str) -> None:
    # `security -i` reads the command from stdin, so the password never appears in a process's arguments.
    # Both values were validated against strict patterns (no quotes, no spaces) before they reach this line.
    done = security("-i", stdin=f'add-generic-password -U -s {SERVICE} -a "{address}" -T /usr/bin/security '
                                f'-w "{password}"\n')
    if done.returncode != 0 or "error" in (done.stderr or "").lower():
        raise Fail("the Keychain refused the item: " + (done.stderr or "").strip()[:200])


def connect(cfg: dict) -> imaplib.IMAP4:
    host, port = cfg.get("host", "imap.gmail.com"), int(cfg.get("port", 993))
    try:
        box = imaplib.IMAP4_SSL(host, port, timeout=30) if cfg.get("ssl", True) else imaplib.IMAP4(host, port, timeout=30)
        box.login(cfg["email"], keychain_password(cfg["email"]))
    except imaplib.IMAP4.error as exc:
        raise Fail(f"login refused for {cfg['email']}: the app password was revoked or mistyped "
                   f"({str(exc)[:120]}); ask the builder to connect jobs-inbox mail again") from None
    except OSError as exc:
        raise Fail(f"cannot reach {host}:{port}: {exc}") from None
    return box


def all_mail(box: imaplib.IMAP4) -> str:
    """The folder flagged \\All (Gmail's All Mail under any UI language), else INBOX."""
    typ, rows = box.list()
    for row in rows or []:
        line = row.decode(errors="replace") if isinstance(row, bytes) else str(row)
        if "\\All" in line.split(")")[0]:
            name = line.rsplit(" ", 1)[-1] if not line.endswith('"') else '"' + line.rstrip('"').rsplit('"', 1)[-1] + '"'
            return name
    return "INBOX"


def examine(box: imaplib.IMAP4, folder: str) -> None:
    typ, _ = box.select(folder, readonly=True)
    if typ != "OK":
        raise Fail(f"cannot open {folder} read-only")


def either(terms: list[str]) -> str:
    out = terms[0]
    for term in terms[1:]:
        out = f"OR {out} {term}"
    return out


def quote(value: str) -> str:
    return '"' + value.replace("\\", "").replace('"', "") + '"'


def criteria(cfg: dict, since: dt.date, domains: list[str], words: list[str]) -> str:
    parts = [f"SINCE {since.strftime('%d-%b-%Y')}", f"NOT FROM {quote(cfg['email'])}"]
    terms = [f"FROM {quote('@' + d)}" for d in domains] + [f"TEXT {quote(w)}" for w in words]
    if terms:
        parts.append(f"({either(terms)})" if len(terms) > 1 else terms[0])
    return " ".join(parts)


def sender_domain(value: str) -> str:
    addr = email.utils.parseaddr(value or "")[1]
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def header_rows(box: imaplib.IMAP4, uids: list[bytes]) -> list[dict]:
    rows = []
    for uid in uids:
        typ, data = box.uid("FETCH", uid.decode(), "(INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            continue
        meta, raw = data[0]
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        stamp = imaplib.Internaldate2tuple(meta)
        epoch = time.mktime(stamp) if stamp else 0.0
        when = dt.datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="minutes") if stamp else ""
        rows.append({"uid": uid.decode(), "date": when,
                     "from_domain": sender_domain(str(msg.get("From", ""))), "subject": str(msg.get("Subject", ""))[:200],
                     "_epoch": epoch})
    return rows


def search(args) -> dict:
    cfg = load_config()
    domains = [d.lower().lstrip("@") for d in args.from_ or []]
    if bad := [d for d in domains if not DOMAIN_RE.match(d)]:
        raise Fail(f"not a sender domain: {', '.join(bad)}", 2)
    now = dt.datetime.now()
    if args.minutes:
        cutoff = now - dt.timedelta(minutes=args.minutes)
        since = cutoff.date()
    else:
        since = dt.date.fromisoformat(args.since)
        cutoff = dt.datetime.combine(since, dt.time())
    box = connect(cfg)
    try:
        folder = all_mail(box)
        examine(box, folder)
        typ, data = box.uid("SEARCH", criteria(cfg, since, domains, args.text or []))
        if typ != "OK":
            raise Fail("the server refused the search")
        uids = (data[0] or b"").split()
        rows = header_rows(box, uids[-max(args.limit * 3, args.limit):])
    finally:
        box.logout()
    rows = [r for r in rows if not args.minutes or r["_epoch"] >= cutoff.timestamp()]
    rows.sort(key=lambda r: r["_epoch"], reverse=True)
    for r in rows:
        r.pop("_epoch")
    return {"folder": folder.strip('"'), "messages": rows[:args.limit]}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style")
        if tag in ("br", "p", "div", "tr", "li"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style") and self.skip > 0

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def body_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        parser = _Text()
        parser.feed(text)
        text = "".join(parser.out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:BODY_LIMIT]


def read(args) -> dict:
    if not args.uid.isdigit():
        raise Fail("UID is a number from search", 2)
    cfg = load_config()
    box = connect(cfg)
    try:
        examine(box, all_mail(box))
        typ, data = box.uid("FETCH", args.uid, "(BODY.PEEK[])")
    finally:
        box.logout()
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        raise Fail(f"no message with uid {args.uid}", 1)
    msg = email.message_from_bytes(data[0][1], policy=email.policy.default)
    return {"uid": args.uid, "date": str(msg.get("Date", "")), "from_domain": sender_domain(str(msg.get("From", ""))),
            "subject": str(msg.get("Subject", ""))[:200], "body": body_text(msg)}


def status(_args) -> dict:
    cfg = load_config()
    connect(cfg).logout()
    return {"configured": True, "email": cfg["email"], "login": "ok"}


def dialog(prompt: str, default: str = "", hidden: bool = False) -> str:
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = (f'display dialog "{esc(prompt)}" default answer "{esc(default)}"'
              f'{" with hidden answer" if hidden else ""} with title "Hermes: jobs-inbox mail" '
              f'buttons {{"Cancel", "OK"}} default button "OK"')
    done = subprocess.run(["osascript", "-e", script, "-e", "text returned of result"], capture_output=True, text=True,
                          timeout=900)
    if done.returncode != 0:
        raise Fail("setup cancelled in the dialog", 1)
    return done.stdout.rstrip("\n")


def setup(args) -> dict:
    address = (args.email or "").strip() or dialog(
        "Gmail address where companies answer your applications:").strip()
    if not EMAIL_RE.match(address):
        raise Fail(f"not an e-mail address: {address!r}", 2)
    subprocess.run(["open", APP_PASSWORD_URL], capture_output=True)
    cfg = {"email": address, "host": "imap.gmail.com", "port": 993}
    for attempt in (1, 2):
        typed = dialog(f"Your browser opened Google's App passwords page for {address}.\n\n"
                       "Create one named Hermes, copy the 16 letters and paste them here. "
                       "jobs-inbox only reads mail; it never sends, moves or deletes.", hidden=True)
        password = re.sub(r"\s+", "", typed).lower()
        if not APP_PW_RE.match(password):
            if attempt == 2:
                raise Fail("an app password is 16 letters; none was stored", 2)
            continue
        box = imaplib.IMAP4_SSL(cfg["host"], cfg["port"], timeout=30)
        try:
            box.login(address, password)
            box.logout()
        except imaplib.IMAP4.error:
            if attempt == 2:
                raise Fail("Google refused that app password twice; none was stored", 3) from None
            continue
        keychain_store(address, password)
        config_path().write_text(json.dumps(cfg, indent=2) + "\n")
        return {"configured": True, "email": address, "login": "ok", "keychain": SERVICE}
    raise Fail("setup did not finish", 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--email")
    sub.add_parser("status")
    s = sub.add_parser("search")
    when = s.add_mutually_exclusive_group(required=True)
    when.add_argument("--since")
    when.add_argument("--minutes", type=int)
    s.add_argument("--from", dest="from_", action="append")
    s.add_argument("--text", action="append")
    s.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("read")
    s.add_argument("uid")
    for p in sub.choices.values():
        p.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        out = {"setup": setup, "status": status, "search": search, "read": read}[args.cmd](args)
    except Fail as exc:
        print(json.dumps({"error": str(exc)}) if args.json else str(exc))
        return exc.code
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}) if args.json else str(exc))
        return 2
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif args.cmd == "search":
        for r in out["messages"]:
            print(f"{r['uid']}  {r['date']}  {r['from_domain']}  {r['subject']}")
        if not out["messages"]:
            print("no messages")
    elif args.cmd == "read":
        print(f"{out['date']}  {out['from_domain']}\n{out['subject']}\n\n{out['body']}")
    else:
        print(" ".join(f"{k}: {v}" for k, v in out.items()))
    return 0 if args.cmd != "search" or out["messages"] else 1


if __name__ == "__main__":
    sys.exit(main())

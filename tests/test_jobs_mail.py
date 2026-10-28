"""triaging-inbox mail.py: jobs-inbox reads job mail over IMAP, read-only, with the app password in the Keychain.

A small IMAP server on localhost speaks the commands Gmail answers; a fake `security` on PATH plays the Keychain.
The tests drive mail.py as jobs-inbox does (subprocess, $HERMES_HOME = the bot's profile) and fail when it could change
the mailbox, miss archived mail, leak a sender's address, or log in with the wrong secret.
"""
import datetime as dt
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MAIL = REPO / "squads" / "jobs" / "skills" / "triaging-inbox" / "scripts" / "mail.py"
CODE_WAIT = REPO / "squads" / "jobs" / "skills" / "submitting-applications" / "scripts" / "code_wait.py"
USER, PASSWORD = "cand@example.com", "abcdabcdabcdabcd"


def message(sender: str, subject: str, body: str, date: str) -> bytes:
    return (f"From: Recruiter Name <{sender}>\r\nTo: {USER}\r\nSubject: {subject}\r\nDate: {date}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n").encode()


# uid -> (internaldate, raw, folder-visible-in-INBOX)
MAILBOX = {
    1: ("01-Oct-2026 09:00:00 +0000", message("noreply@greenhouse-mail.io", "Old", "old", "Thu, 1 Oct 2026"), True),
    2: ("20-Oct-2026 10:00:00 +0000", message("talent@acme.example", "Acme: next steps",
                                              "We would like a 30-minute call next week.", "Tue, 20 Oct 2026"), False),
    3: ("21-Oct-2026 11:00:00 +0000", message(USER, "Re: Acme", "my own sent reply", "Wed, 21 Oct 2026"), True),
    4: ("22-Oct-2026 12:00:00 +0000", message("no-reply@greenhouse-mail.io", "Security code",
                                              "Your code is aB3dE9fG", "Thu, 22 Oct 2026"), True),
}


class Imap(socketserver.StreamRequestHandler):
    log: list = []

    def send(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self):
        self.send("* OK test IMAP ready")
        folder = None
        while line := self.rfile.readline().decode().rstrip("\r\n"):
            tag, cmd, *rest = line.split(" ", 2)
            arg = rest[0] if rest else ""
            Imap.log.append(f"{cmd.upper()} {arg}")
            up = cmd.upper()
            if up == "CAPABILITY":
                self.send("* CAPABILITY IMAP4rev1")
                self.send(f"{tag} OK done")
            elif up == "LOGIN":
                ok = arg == f'{USER} "{PASSWORD}"' or arg == f"{USER} {PASSWORD}"
                self.send(f"{tag} OK done" if ok else f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
            elif up == "LIST":
                self.send('* LIST (\\HasNoChildren) "/" "INBOX"')
                self.send('* LIST (\\All \\HasNoChildren) "/" "[Gmail]/Todos"')
                self.send(f"{tag} OK done")
            elif up in ("EXAMINE", "SELECT"):
                folder = arg.strip('"')
                self.send(f"* {len(MAILBOX)} EXISTS")
                self.send(f"{tag} OK [READ-{'ONLY' if up == 'EXAMINE' else 'WRITE'}]")
            elif up == "UID" and arg.upper().startswith("SEARCH"):
                crit = arg[7:]
                hits = []
                for uid, (_, raw, in_inbox) in MAILBOX.items():
                    text = raw.decode()
                    sender = re.search(r"<([^>]+)>", text).group(1)
                    if folder == "INBOX" and not in_inbox:
                        continue
                    if "SINCE 15-Oct-2026" in crit and uid == 1:
                        continue
                    if f'NOT FROM "{USER}"' in crit and sender == USER:
                        continue
                    froms = re.findall(r'FROM "@([^"]+)"', crit)
                    if froms and not any(sender.endswith("@" + d) for d in froms):
                        continue
                    hits.append(str(uid))
                self.send("* SEARCH " + " ".join(hits))
                self.send(f"{tag} OK done")
            elif up == "UID" and arg.upper().startswith("FETCH"):
                _, uid, what = arg.split(" ", 2)
                date, raw, _ = MAILBOX[int(uid)]
                if "HEADER.FIELDS" in what:
                    data = raw.split(b"\r\n\r\n")[0] + b"\r\n\r\n"
                    head = f'* {uid} FETCH (UID {uid} INTERNALDATE "{date}" BODY[HEADER.FIELDS (FROM SUBJECT DATE)] '
                else:
                    data = raw
                    head = f"* {uid} FETCH (UID {uid} BODY[] "
                self.wfile.write(head.encode() + b"{" + str(len(data)).encode() + b"}\r\n" + data + b")\r\n")
                self.send(f"{tag} OK done")
            elif up == "LOGOUT":
                self.send("* BYE")
                self.send(f"{tag} OK done")
                return
            else:
                self.send(f"{tag} BAD unexpected {up}")


@pytest.fixture
def server():
    Imap.log = []
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Imap)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def bot_env(tmp_path: Path, port: int, secret: str = PASSWORD) -> dict:
    """jobs-inbox's environment: its profile as HERMES_HOME holding mail.json, and a Keychain that knows the secret."""
    home = tmp_path / "profiles" / "jobs-inbox"
    home.mkdir(parents=True)
    (home / "mail.json").write_text(json.dumps({"email": USER, "host": "127.0.0.1", "port": port, "ssl": False}))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "security"
    fake.write_text('#!/bin/sh\n[ "$1" = find-generic-password ] && [ "$3" = hermes-jobs-inbox-imap ] && '
                    f'[ "$5" = "{USER}" ] && echo "{secret}" && exit 0\nexit 44\n')
    fake.chmod(0o755)
    return {**os.environ, "HERMES_HOME": str(home), "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}


def mail(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(MAIL), *args], capture_output=True, text=True, env=env,
                          timeout=60)


def test_search_reads_all_mail_read_only_and_skips_the_users_own_mail(tmp_path, server):
    env = bot_env(tmp_path, server)
    p = mail(env, "search", "--since", "2026-10-15", "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout)
    assert out["folder"] == "[Gmail]/Todos", "archived replies live only in All Mail"
    assert [m["uid"] for m in out["messages"]] == ["4", "2"], "newest first, the old one and the sent one left out"
    acme = out["messages"][1]
    assert dt.datetime.fromisoformat(acme.pop("date")) == dt.datetime(2026, 10, 20, 10, tzinfo=dt.timezone.utc)
    assert acme == {"uid": "2", "from_domain": "acme.example", "subject": "Acme: next steps"}
    assert "Recruiter Name" not in p.stdout and "talent@" not in p.stdout, "no sender name or address in a listing"
    verbs = {entry.split(" ")[0] for entry in Imap.log}
    assert "SELECT" not in verbs and "EXAMINE" in verbs, "the mailbox is opened read-only"
    assert not {"STORE", "COPY", "MOVE", "EXPUNGE", "APPEND"} & verbs


def test_read_returns_the_body_without_marking_it_seen(tmp_path, server):
    env = bot_env(tmp_path, server)
    p = mail(env, "read", "2", "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout)
    assert "30-minute call" in out["body"] and out["from_domain"] == "acme.example"
    fetches = [e for e in Imap.log if e.startswith("UID FETCH")]
    assert fetches and all("BODY.PEEK" in e for e in fetches), "a plain BODY[] fetch would mark the mail read"


def test_a_code_search_is_bounded_to_the_sender_domain(tmp_path, server):
    env = bot_env(tmp_path, server)
    p = mail(env, "search", "--since", "2026-10-15", "--from", "greenhouse-mail.io", "--json")
    assert [m["uid"] for m in json.loads(p.stdout)["messages"]] == ["4"]
    assert mail(env, "search", "--since", "2026-10-15", "--from", "evil.example/../x").returncode == 2


def test_a_revoked_app_password_says_how_to_fix_it(tmp_path, server):
    env = bot_env(tmp_path, server, secret="zzzzzzzzzzzzzzzz")
    p = mail(env, "status", "--json")
    assert p.returncode == 3
    assert "login refused" in json.loads(p.stdout)["error"] and "builder" in p.stdout


def test_without_setup_the_bot_is_told_mail_is_not_connected(tmp_path):
    home = tmp_path / "profiles" / "jobs-inbox"
    home.mkdir(parents=True)
    p = mail({**os.environ, "HERMES_HOME": str(home)}, "status", "--json")
    assert p.returncode == 1 and "not connected" in json.loads(p.stdout)["error"]


def test_code_wait_reports_the_mail_gap_at_once(tmp_path):
    """The applier's code request fails in seconds, naming the fix, when jobs-inbox has no mail account."""
    root = tmp_path / "root"
    installed = root / "profiles" / "jobs-inbox" / "skills" / "squad-jobs" / "triaging-inbox" / "scripts"
    installed.mkdir(parents=True)
    shutil.copy(MAIL, installed / "mail.py")  # what apply installs; no mail.json yet
    folder = tmp_path / "project"
    folder.mkdir()
    env = {**os.environ, "HERMES_HOME": str(root)}
    p = subprocess.run([sys.executable, "-B", str(CODE_WAIT), "--project", str(folder), "--opening",
                        "JOB-20261020-acme-analyst", "--site", "greenhouse-mail.io", "--json"],
                       capture_output=True, text=True, env=env, timeout=60)
    out = json.loads(p.stdout)
    assert p.returncode == 3 and out["outcome"] == "unavailable"
    assert "mail is not connected" in out["reason"] and "connectors" not in out["reason"]

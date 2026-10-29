"""Tab hygiene for a shared, signed-in browser that several Hermes bots drive at once.

Standard library only: the Hermes plugin imports it, and so does the no-agent sweep cron under a plain python3.

A bot reaches the shared browser through `browser.cdp_url`. Hermes then runs one browser-harness daemon per
`browser_exec` session name, each attached to its own tab, and never stops those daemons on a CDP override, so
their tabs stay open. This module:

- names a session per Hermes task, so every bot run gets its own daemon and tab (`session_name`);
- records a lease per session name (`touch_lease`), holding the Hermes pid;
- at the end of a turn stops that session's daemon and closes exactly the tabs it held (`release`);
- sweeps leftovers: daemons whose lease is stale or whose Hermes pid is gone, then tabs nobody holds (`sweep`).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import signal
import socket
import struct
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PREFIX = "sb-"  # session names this module creates; a name the model chose is still leased and released


# --- endpoint ------------------------------------------------------------------------------------------------

def loopback_port(cdp_url: str) -> int | None:
    """The port of a loopback CDP URL (http, ws), or None: only a local shared browser is managed."""
    try:
        parts = urllib.parse.urlsplit(cdp_url or "")
    except ValueError:
        return None
    if parts.hostname not in ("127.0.0.1", "localhost", "::1") or not parts.port:
        return None
    return parts.port


def leases_dir(port: int) -> Path:
    """One lease directory per shared browser, keyed by port, under the Hermes root."""
    root = Path(os.environ.get("HERMES_SHARED_BROWSER_STATE") or Path.home() / ".hermes" / "browser-sessions")
    return root / f"leases-{port}"


# --- minimal CDP over a browser-level websocket ----------------------------------------------------------------

class Cdp:
    """Browser-target CDP client: one connection, request/response by id, events ignored.

    `ws_url` connects to a page target's own websocket instead of the browser one, so page-domain methods
    (Page.navigate, Runtime.evaluate) work directly; used by tests and by nothing on the bot path.
    """

    def __init__(self, port: int, timeout: float = 5.0, ws_url: str | None = None):
        if not ws_url:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
                ws_url = json.load(r)["webSocketDebuggerUrl"]
        parts = urllib.parse.urlsplit(ws_url)
        self.sock = socket.create_connection((parts.hostname, parts.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path} HTTP/1.1\r\nHost: {parts.hostname}:{parts.port}\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("CDP handshake closed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _recv_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("CDP connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self) -> tuple[int, bytes]:
        b0, b1 = self._recv_exact(2)
        size = b1 & 0x7F
        if size == 126:
            size = struct.unpack(">H", self._recv_exact(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", self._recv_exact(8))[0]
        return b0 & 0x0F, self._recv_exact(size)

    def send(self, method: str, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        size = len(data)
        head = bytes([0x81]) + (bytes([0x80 | size]) if size < 126 else
                                bytes([0x80 | 126]) + struct.pack(">H", size) if size < 65536 else
                                bytes([0x80 | 127]) + struct.pack(">Q", size))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        text = b""
        while True:
            op, payload = self._frame()
            if op == 8:
                raise ConnectionError("CDP connection closed by the browser")
            if op in (1, 0):
                text += payload
                try:
                    msg = json.loads(text)
                except ValueError:
                    continue  # fragmented frame
                text = b""
                if msg.get("id") == self.n:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error'].get('message')}")
                    return msg.get("result", {})

    def pages(self) -> list[dict]:
        return [t for t in self.send("Target.getTargets")["targetInfos"] if t.get("type") == "page"]

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


BLANK = "about:blank"


def page_states(port: int) -> dict[str, tuple[bool, str]]:
    """targetId -> (attached, url), for every page of the shared browser."""
    cdp = Cdp(port)
    try:
        return {t["targetId"]: (bool(t.get("attached")), t.get("url") or "") for t in cdp.pages()}
    finally:
        cdp.close()


def keep_anchor(candidates: list[str], states: dict[str, tuple[bool, str]]) -> list[str]:
    """Never close the last blank page: a harness daemon that starts attaches to an existing page, and a shared blank
    anchor keeps it off another bot's tab and stops it from creating a page of its own."""
    blanks = [tid for tid, (_a, url) in states.items() if url == BLANK]
    if blanks and all(tid in candidates for tid in blanks):
        candidates = [tid for tid in candidates if tid != blanks[0]]
    return candidates


def close_targets(port: int, ids) -> int:
    ids = list(ids)
    if not ids:
        return 0
    cdp = Cdp(port)
    closed = []
    try:
        for tid in ids:
            try:
                cdp.send("Target.closeTarget", targetId=tid)
                closed.append(tid)
            except (RuntimeError, OSError):
                pass  # already gone
        # Chrome answers closeTarget before the page is destroyed: wait (bounded) until the pages are gone, so a caller
        # that reads the tabs next never sees one it just closed.
        deadline = time.monotonic() + 2.0
        while closed and time.monotonic() < deadline:
            if not set(closed) & {t["targetId"] for t in cdp.pages()}:
                break
            time.sleep(0.05)
    finally:
        cdp.close()
    return len(closed)


# --- session names and leases ------------------------------------------------------------------------------------

def session_name(task_id: str, session_id: str) -> str:
    """Stable per-task browser_exec session name: one daemon and one tab per bot run."""
    seed = task_id or session_id or str(os.getpid())
    return PREFIX + hashlib.sha256(seed.encode()).hexdigest()[:12]


def touch_lease(port: int, name: str, pid: int | None = None) -> None:
    if not SESSION_RE.match(name or ""):
        return
    d = leases_dir(port)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(str(pid or os.getpid()))


def drop_lease(port: int, name: str) -> None:
    try:
        (leases_dir(port) / name).unlink()
    except OSError:
        pass


def leases(port: int) -> dict[str, tuple[int, float]]:
    """name -> (Hermes pid, age in seconds)."""
    d, out, now = leases_dir(port), {}, time.time()
    if d.is_dir():
        for p in d.iterdir():
            try:
                out[p.name] = (int(p.read_text().strip() or 0), now - p.stat().st_mtime)
            except (OSError, ValueError):
                continue
    return out


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:  # a child of this process that exited is a zombie until reaped: reap it so it reads as gone
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --- harness daemons -------------------------------------------------------------------------------------------

def harness_runtime_dir() -> Path:
    raw = os.environ.get("BH_RUNTIME_DIR")
    if raw:
        return Path(raw).expanduser()
    home = os.environ.get("BH_HOME") or os.environ.get("BROWSER_HARNESS_HOME")
    base = Path(home).expanduser() if home else (Path(os.environ["XDG_CONFIG_HOME"]) / "browser-harness"
                                                  if os.environ.get("XDG_CONFIG_HOME")
                                                  else Path.home() / ".config" / "browser-harness")
    return base / "runtime"


def daemon_pid(name: str) -> int | None:
    """The browser-harness daemon pid serving BU_NAME `name`, verified by its command line."""
    try:
        pid = int((harness_runtime_dir() / f"bu-{name}.pid").read_text().strip())
    except (OSError, ValueError):
        return None
    if not pid_alive(pid):
        return None
    try:
        import subprocess
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, ValueError):
        return None
    return pid if "browser_harness.daemon" in cmd else None


def stop_daemon(name: str, wait: float = 5.0) -> bool:
    """SIGTERM the verified daemon of `name`; True when it is gone (or was never running)."""
    pid = daemon_pid(name)
    if pid is None:
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return not pid_alive(pid)


# --- release and sweep -----------------------------------------------------------------------------------------

def release(port: int, names, settle: float = 1.0, held=None) -> dict:
    """Stop the daemons of `names`, then close only the tabs those daemons let go. The blank anchor page is kept.

    `held` is what the caller recorded for these sessions (target ids seen attached during their tool calls): only
    those are closed, and only once the stop left them unattached. Without a recording, a tab is closed only when it
    was attached before the stop and free after it — a page that was already free before (another bot's tab whose
    attach has not landed yet, an orphan) is never touched. A tab another bot works in stays attached to its daemon
    and is never closed, so a mis-claimed id cannot cost a live tab.
    """
    names = [n for n in names if SESSION_RE.match(n or "")]
    if not names:
        return {"stopped": 0, "closed": 0}
    before = page_states(port)
    candidates = set(held) if held is not None else {tid for tid, (attached, _url) in before.items() if attached}
    stopped = sum(1 for n in names if stop_daemon(n))
    time.sleep(settle)
    after = page_states(port)
    free = [tid for tid in candidates if tid in after and not after[tid][0]]
    closed = close_targets(port, keep_anchor(free, after))
    for n in names:
        drop_lease(port, n)
    return {"stopped": stopped, "closed": closed}


def claimed_targets(port: int, before: dict[str, bool]) -> set[str]:
    """Targets a tool call of this session put in hand: attached now, and either new or unattached in `before`.

    The daemon of a session attaches its tab during the call, so the diff of `Target.getTargets` around the call
    names that session's tabs without asking the daemon.
    """
    return {tid for tid, (attached, _url) in page_states(port).items()
            if attached and not before.get(tid, False)}


def attached_now(port: int) -> dict[str, bool]:
    """targetId -> attached, the snapshot `claimed_targets` diffs against."""
    return {tid: attached for tid, (attached, _url) in page_states(port).items()}


def sweep(port: int, max_idle: float = 3 * 3600, settle: float = 30.0) -> dict:
    """Leftovers after a crash or a killed bot: stop daemons whose lease is stale or whose Hermes process is gone,
    then close every page nobody holds in two checks `settle` seconds apart. The blank anchor page is kept.

    This is the only place that closes pages it never saw attached: a crash can leave a tab no daemon holds. `settle`
    is 30 s so a tab another bot just created has time to be attached (its daemon attaches within milliseconds; the
    margin covers a slow start). A page attached in either check is kept.
    """
    stale = [n for n, (pid, age) in leases(port).items() if age > max_idle or not pid_alive(pid)]
    stopped = 0
    for n in stale:
        if stop_daemon(n):
            stopped += 1
            drop_lease(port, n)
    first = {tid for tid, (attached, _url) in page_states(port).items() if not attached}
    time.sleep(settle)
    states = page_states(port)
    free = keep_anchor([tid for tid in first if tid in states and not states[tid][0]], states)
    if not any(url == BLANK for _a, url in states.values()):
        open_blank(port)
    return {"stale_sessions": len(stale), "stopped": stopped, "closed": close_targets(port, free),
            "pages_left": len(states) - len(free)}


def open_blank(port: int) -> None:
    """Recreate the blank anchor page."""
    cdp = Cdp(port)
    try:
        cdp.send("Target.createTarget", url=BLANK)
    finally:
        cdp.close()


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Show the tabs and session leases of the shared browser "
                                             "(the plugin and the sweep import this module).")
    ap.add_argument("--port", type=int, default=9333, help="CDP port of the shared browser (default 9333)")
    args = ap.parse_args(argv)
    try:
        states = page_states(args.port)
    except OSError as exc:
        print(json.dumps({"error": f"shared browser not reachable on port {args.port}: {exc}"}), file=sys.stderr)
        return 1
    held = leases(args.port)
    print(json.dumps({"pages": [{"id": t, "attached": a, "url": u} for t, (a, u) in states.items()],
                      "leases": {n: {"pid": pid, "age_s": round(age)} for n, (pid, age) in held.items()}},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

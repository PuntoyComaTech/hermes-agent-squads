#!/usr/bin/env python3
"""Decide whether the browser-header retry (fetch_page.py) may run for one URL, and the network guard both scripts use.

The retry exists to get past bot-filtering firewalls on sites whose robots.txt permits access. It is never used to
override a site that has said no. A 403 has two very different causes: a firewall default on a site whose published
policy allows access, or a site that has actually declined. This script tells them apart.

Rules (RFC 9309), deliberately on the cautious side:
  * longest match wins; on equal specificity Disallow wins;
  * a Disallow for either "*" or this squad's agent token blocks the retry;
  * blank lines inside a record do not end it (urllib.robotparser drops those rules, which fails open);
  * one leading UTF-8 byte-order mark is skipped (left in, it hides a first User-agent line and drops its group);
  * a 404 means no published policy, which is permission;
  * any other failure to read robots.txt leaves permission unconfirmed, and the retry does not happen, including a
    User-agent, Allow or Disallow line holding U+FFFD (a byte that is not valid UTF-8).

The policy file is read with the agent's own user agent first; if that request is refused, it is read again with a
browser user agent, and the policy is then obeyed strictly. A policy the checker is prevented from reading cannot be
honoured, and robots.txt is not the protected resource.

Network guard. Every request these scripts send goes through guarded_fetch(), which checks each hop before it is sent:
  * the host must not be on the blocklist. linkedin.com is always on it (the squad's browser and web tools never open
    it, and the portal CLI is the one sanctioned reader). JOBS_BLOCKLIST (comma-separated host names) and the
    --blocklist option add more. A blocklisted host is refused by its name, before any DNS lookup;
  * every address the host resolves to must be public. Loopback, private (RFC 1918 and fc00::/7), link-local (the
    169.254.169.254 metadata address included), unspecified, multicast, reserved and shared (100.64.0.0/10) addresses
    are refused. An IPv4-mapped or NAT64-embedded address is judged by the IPv4 address it carries. One refused address
    in the answer refuses the host;
  * the client connects to the address that passed (curl --resolve, or a pinned socket in fetch_page), so there is no
    second lookup between the check and the connection;
  * redirects are not followed by the client. Each Location is checked again as a new hop, so a redirect into a
    private network is refused where it happens. At most MAX_REDIRECTS redirects are followed.

Usage:  python3 robots_check.py <url> [--blocklist HOST ...]
Exit 0 = the retry may proceed. Exit 1 = do not retry; go to the next escalation step (employer's own site).
Exit 2 = usage error.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import socket
import subprocess
import sys
import tempfile
from collections import namedtuple
from pathlib import Path
from typing import Callable, Optional, Sequence
from urllib.parse import unquote, urljoin, urlsplit

AGENT_TOKEN = "hermes-jobs"
HONEST_UA = "hermes-jobs/1.0 (job-search assistant; honours robots.txt)"
BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT = 12
MAX_REDIRECTS = 5
MAX_ROBOTS_BYTES = 1024 * 1024
BLOCKLIST_ENV = "JOBS_BLOCKLIST"
BUILT_IN_BLOCKLIST = ("linkedin.com",)
HOST_ENTRY_RE = re.compile(r"(?:\*\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*")

# Addresses refused whatever the other checks say. The metadata address is also link-local; it is listed by name so
# the rule reads at a glance.
REFUSED_NETWORKS = tuple(ipaddress.ip_network(net) for net in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "169.254.169.254/32",
    "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
    "::/96", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
))
NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")
SIX_TO_FOUR_PREFIX = ipaddress.ip_network("2002::/16")

Target = namedtuple("Target", "host port ip")


class GuardError(RuntimeError):
    """A request refused before any connection: a blocklisted host or an address that is not public."""


# --- the network guard -------------------------------------------------------------------------------------------

def check_address(text) -> Optional[str]:
    """None when the address is public; otherwise the reason it is refused."""
    try:
        ip = ipaddress.ip_address(str(text).split("%", 1)[0])
    except ValueError:
        return f"{text!r} is not an IP address"
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped
        if embedded is None and ip in NAT64_PREFIX:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is None and ip in SIX_TO_FOUR_PREFIX:
            embedded = ipaddress.IPv4Address(ip.packed[2:6])
        if embedded is not None:
            ip = embedded
    for net in REFUSED_NETWORKS:
        if ip.version == net.version and ip in net:
            return f"{ip} is in {net}"
    if not ip.is_global:
        return f"{ip} is not a public address"
    return None


def resolve_host(host: str, port: int) -> list:
    """Every address the host resolves to, in the order given. An IP literal is its own answer."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    seen: list[str] = []
    for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        address = str(info[4][0])
        if address not in seen:
            seen.append(address)
    return seen


def blocked_host(host: str, patterns: Sequence[str]) -> Optional[str]:
    """The blocklist entry that covers this host (the entry itself or any subdomain of it), or None."""
    host = host.lower().rstrip(".")
    for pattern in patterns:
        bare = pattern.lower().lstrip("*").lstrip(".")
        if bare and (host == bare or host.endswith("." + bare)):
            return pattern
    return None


def load_blocklist(extra: Sequence[str] = (), env=None) -> tuple:
    """Built-in entries, then JOBS_BLOCKLIST, then the --blocklist values. Raises ValueError on a non-host entry."""
    source = os.environ if env is None else env
    entries: list[str] = list(BUILT_IN_BLOCKLIST)
    for chunk in [source.get(BLOCKLIST_ENV, "")] + list(extra):
        for item in re.split(r"[\s,]+", chunk or ""):
            item = item.strip().lower()
            if not item:
                continue
            if not HOST_ENTRY_RE.fullmatch(item):
                raise ValueError(f"blocklist entry is not a host name: {item!r}")
            entries.append(item)
    return tuple(dict.fromkeys(entries))


def resolve_target(url: str, blocklist=None, resolver: Optional[Callable] = None) -> Target:
    """The checked target for one request: host, port and the one public address to connect to. Raises GuardError."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise GuardError(f"scheme {scheme!r} is not http(s)")
    try:
        port = parts.port
    except ValueError:
        raise GuardError("the port is not a number") from None
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise GuardError("the URL has no host")
    port = port or (443 if scheme == "https" else 80)
    try:
        patterns = load_blocklist() if blocklist is None else tuple(blocklist)
    except ValueError as exc:
        raise GuardError(str(exc)) from None
    hit = blocked_host(host, patterns)
    if hit:
        raise GuardError(f"{host} is on the squad blocklist (entry {hit})")
    if is_ip_literal(host):
        addresses = [host]  # an address literal is its own answer: never looked up
    else:
        try:
            addresses = (resolver or resolve_host)(host, port)
        except (OSError, UnicodeError, ValueError) as exc:
            raise GuardError(f"{host} does not resolve ({exc.__class__.__name__})") from None
    if not addresses:
        raise GuardError(f"{host} has no address")
    for address in addresses:
        reason = check_address(address)
        if reason:
            raise GuardError(f"{host} resolves to a refused address: {reason}")
    return Target(host, port, str(addresses[0]))


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def resolve_arg(target: Target) -> str:
    """curl --resolve value that pins a host name to the checked address (IPv6 in brackets)."""
    ip = f"[{target.ip}]" if ":" in target.ip else target.ip
    return f"{target.host}:{target.port}:{ip}"


def hop_argv(url: str, out: Path, *, ua: str, accept: str, accept_language: Optional[str] = None,
             target: Optional[Target] = None, timeout: int = 45, max_bytes: int = 10 * 1024 * 1024,
             compressed: bool = True) -> list:
    """One curl request: GET only, no redirect following, the URL after `--`. Prints code, redirect target, size."""
    argv = ["curl", "-sS", "--max-time", str(timeout), "--max-filesize", str(max_bytes)]
    if compressed:
        argv.append("--compressed")
    argv += ["-A", ua, "-H", f"Accept: {accept}"]
    if accept_language:
        argv += ["-H", f"Accept-Language: {accept_language}"]
    if target is not None and not is_ip_literal(target.host):
        argv += ["--resolve", resolve_arg(target)]
    argv += ["-o", str(out), "-w", "%{http_code}\t%{redirect_url}\t%{size_download}", "--", url]
    return argv


def curl_hop(url: str, out: Path, *, ua: str, accept: str, accept_language: Optional[str], target: Target,
             timeout: int, max_bytes: int) -> tuple:
    """(status code, Location or '', bytes) of one hop, through curl pinned to the checked address."""
    argv = hop_argv(url, out, ua=ua, accept=accept, accept_language=accept_language, target=target,
                    timeout=timeout, max_bytes=max_bytes)
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout + 15)
    if proc.returncode != 0:
        raise RuntimeError(f"curl exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    code, location, size = (proc.stdout.strip("\n").split("\t") + ["", "0"])[:3]
    return int(code or 0), location, int(size or 0)


def guarded_fetch(url: str, out: Path, *, ua: str, accept: str, accept_language: Optional[str] = None,
                  blocklist=None, hop: Optional[Callable] = None, resolver: Optional[Callable] = None,
                  timeout: int = FETCH_TIMEOUT, max_bytes: int = MAX_ROBOTS_BYTES,
                  max_redirects: int = MAX_REDIRECTS) -> tuple:
    """GET with the guard applied to every hop. Returns (status code, bytes of the final body). Raises GuardError.

    hop and resolver are seams for tests: the real defaults are curl and the system resolver.
    """
    run = hop or curl_hop
    current = url
    for _ in range(max_redirects + 1):
        target = resolve_target(current, blocklist, resolver)
        code, location, size = run(current, out, ua=ua, accept=accept, accept_language=accept_language,
                                   target=target, timeout=timeout, max_bytes=max_bytes)
        if 300 <= code < 400 and location:
            current = urljoin(current, location)
            continue
        return code, size
    raise RuntimeError(f"more than {max_redirects} redirects")


# --- robots.txt ----------------------------------------------------------------------------------------------------

def _fetch(url: str, ua: str, blocklist=None) -> tuple:
    """(body text, status code) of one robots.txt GET, every hop guarded. Raises GuardError when refused."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "robots.txt"
        code, _size = guarded_fetch(url, out, ua=ua, accept="text/plain,*/*", blocklist=blocklist,
                                    timeout=FETCH_TIMEOUT, max_bytes=MAX_ROBOTS_BYTES)
        body = out.read_bytes().decode("utf-8", errors="replace") if out.exists() else ""
    return body, code


def is_robots_body(text: str) -> bool:
    """Does this look like a robots.txt?

    A misconfigured host can answer /robots.txt with 200 and an HTML error page. That body parses to zero rules,
    and zero rules read as "allowed", which would grant permission that was never given. An empty or whitespace-only
    body IS an allow-all under RFC 9309; a non-empty body with no recognised directive is unreadable.
    """
    text = text.removeprefix("\ufeff")
    if not text.strip():
        return True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if ":" in line and line.split(":", 1)[0].strip() in (
            "user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host",
        ):
            return True
    return False


def has_undecodable_rule(text: str) -> bool:
    """Does a User-agent, Allow or Disallow line hold U+FFFD?

    U+FFFD stands in for a byte that did not decode as UTF-8. A rule with such a byte can never match, so it would be
    skipped and the path read as allowed. Such a body is unreadable, not permissive. U+FFFD in a comment or in any
    other field decides nothing and is ignored.
    """
    for raw in text.removeprefix("\ufeff").splitlines():
        line = raw.split("#", 1)[0]
        if "\ufffd" in line and ":" in line:
            field = line.split(":", 1)[0].replace("\ufffd", "").strip().lower()
            if field in ("user-agent", "allow", "disallow"):
                return True
    return False


def _groups(text: str) -> dict:
    """user-agent -> [(is_allow, pattern)], tolerating blank lines inside a record."""
    out, agents, expect = {}, [], True
    for raw in text.removeprefix("\ufeff").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not expect:
                agents, expect = [], True
            agents.append(value.lower())
            out.setdefault(value.lower(), [])
        elif field in ("allow", "disallow") and agents:
            expect = False
            for agent in agents:
                out[agent].append((field == "allow", value))
    return out


def _match(pattern: str, path: str) -> int:
    """RFC 9309 wildcard match; returns the match length or -1.

    The pattern is percent-decoded to match the decoded path, so "Disallow: /foo%20bar" matches "/foo bar". Under RFC
    9309 section 2.2.2, "$" anchors the end only at the end of the pattern; mid-pattern "$" is literal.
    """
    if pattern == "":
        return -1
    pattern = unquote(pattern)
    end_anchor = pattern.endswith("$")
    pat = pattern[:-1] if end_anchor else pattern
    rx = "^" + "".join(".*" if c == "*" else re.escape(c) for c in pat) + ("$" if end_anchor else "")
    return len(pattern) if re.match(rx, path) else -1


def allowed(text: str, agent: str, path: str) -> bool:
    groups = _groups(text)
    rules = groups.get(agent.lower()) or groups.get("*") or []
    best_len, best_allow = -1, True
    for is_allow, pat in rules:
        n = _match(pat, path)
        if n > best_len or (n == best_len and n >= 0 and not is_allow):
            best_len, best_allow = n, is_allow  # ties go to Disallow (cautious)
    return True if best_len < 0 else best_allow


def gate(url: str, blocklist=None):
    """(exit code, one-line message). 0 = the browser-header retry may run; 1 = it may not.

    blocklist: the host patterns to refuse (None = built-in plus JOBS_BLOCKLIST).
    """
    parts = urlsplit(url)
    path = unquote(parts.path) or "/"
    if parts.query:
        path += "?" + unquote(parts.query)
    robots = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        resolve_target(robots, blocklist)  # refused before any request to the host
    except GuardError as exc:
        return 1, f"REFUSED - {exc}; do not retry; use the employer's own posting instead"
    body, last = None, "no attempt"
    for ua in (HONEST_UA, BROWSER):
        try:
            text, code = _fetch(robots, ua, blocklist)
        except GuardError as exc:
            return 1, f"REFUSED - {exc}; do not retry; use the employer's own posting instead"
        except Exception as exc:  # noqa: BLE001 - any transport failure leaves permission unconfirmed
            last = type(exc).__name__
            continue
        if code == 404:
            return 0, "ALLOWED - no robots.txt published"
        if code == 200:
            if not is_robots_body(text):
                last = "HTTP 200 but the body is not a robots.txt"
                continue
            if has_undecodable_rule(text):
                last = "HTTP 200 but a User-agent/Allow/Disallow line is not valid UTF-8"
                continue
            body = text
            break
        last = f"HTTP {code}"
    if body is None:
        return 1, f"UNCONFIRMED ({last}) - do not retry; use the employer's own posting instead"
    for agent in (AGENT_TOKEN, "*"):
        if not allowed(body, agent, path):
            return 1, f"DISALLOWED for {agent} - do not retry; use the employer's own posting instead"
    return 0, "ALLOWED - robots.txt permits this path"


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Decide whether the browser-header retry may run for a URL (robots.txt).")
    parser.add_argument("url", help="the posting URL (http or https)")
    parser.add_argument("--blocklist", action="append", default=[],
                        help="a host to refuse, in addition to linkedin.com and JOBS_BLOCKLIST (repeatable)")
    args = parser.parse_args(argv)
    if urlsplit(args.url).scheme.lower() not in ("http", "https"):
        print("robots_check: only http(s) URLs are checked", file=sys.stderr)
        return 2
    try:
        blocklist = load_blocklist(args.blocklist)
    except ValueError as exc:
        print(f"robots_check: {exc}", file=sys.stderr)
        return 2
    code, message = gate(args.url, blocklist)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())

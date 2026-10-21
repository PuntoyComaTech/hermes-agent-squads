"""The network guard of the jobs squad's fetch scripts: the host blocklist and the address rule, offline.

Nothing here opens a socket or resolves a real name. Addresses are checked as text, the resolver is replaced with a
table, and every hop is a fake. The one exception is the subprocess group at the end: those runs use IP literals and
blocklisted names, which the guard refuses before any lookup, so they need no network either.

The addresses: loopback, the RFC 1918 ranges, link-local, the cloud metadata address 169.254.169.254, IPv6 ::1,
fc00::/7, and the IPv4-mapped and NAT64 forms of the same.

Python 3.9 compatible and stdlib only; runs under pytest or `python3 -m unittest`.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fetch_page  # noqa: E402
import robots_check  # noqa: E402
from robots_check import GuardError  # noqa: E402

METADATA = "169.254.169.254"
REFUSED_ADDRESSES = [
    "127.0.0.1", "127.8.9.10", "10.0.0.5", "172.16.0.1", "172.31.255.254", "192.168.1.1",
    "169.254.169.254", "169.254.1.1", "100.64.0.1", "0.0.0.0", "::1", "::", "fc00::1", "fd12:3456::5",
    "fe80::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254", "::ffff:10.0.0.5", "64:ff9b::a9fe:a9fe",
    "2002:7f00:1::1", "ff02::1",
]
PUBLIC_ADDRESSES = ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"]
PUBLIC = "93.184.216.34"


def table_resolver(table):
    """A resolver that answers from a table, and fails for any name it does not know (no real DNS is ever asked)."""
    def resolve(host, port):
        if host not in table:
            raise OSError(f"no such host in the test table: {host}")
        return list(table[host])
    return resolve


class HopRecorder:
    """Stands in for curl_hop. `answers` maps an exact URL to (code, Location). Each call is recorded in order."""

    def __init__(self, answers=None, default=(200, "")):
        self.answers = answers or {}
        self.default = default
        self.requested = []
        self.targets = []

    def __call__(self, url, out, *, ua, accept, accept_language, target, timeout, max_bytes):
        self.requested.append(url)
        self.targets.append(target)
        code, location = self.answers.get(url, self.default)
        if code == 200:
            out.write_bytes(b"<html><h1>Senior Data Engineer</h1></html>")
        return code, location, 0 if code != 200 else 40


# --- the address rule -----------------------------------------------------------------------------------------

class AddressRuleTests(unittest.TestCase):
    def test_every_named_private_loopback_link_local_and_metadata_address_is_refused(self):
        for address in REFUSED_ADDRESSES:
            with self.subTest(address=address):
                self.assertIsNotNone(robots_check.check_address(address), address)

    def test_public_addresses_are_allowed(self):
        for address in PUBLIC_ADDRESSES:
            with self.subTest(address=address):
                self.assertIsNone(robots_check.check_address(address), address)

    def test_the_metadata_address_has_its_own_reason(self):
        self.assertIn("169.254", robots_check.check_address(METADATA))

    def test_a_scoped_ipv6_link_local_address_is_still_refused(self):
        self.assertIsNotNone(robots_check.check_address("fe80::1%en0"))


# --- resolution: one refused address refuses the host ---------------------------------------------------------

class ResolutionTests(unittest.TestCase):
    def test_a_name_that_resolves_to_the_metadata_address_is_refused(self):
        resolver = table_resolver({"jobs.example.com": [METADATA]})
        with self.assertRaises(GuardError) as err:
            robots_check.resolve_target("https://jobs.example.com/job/1", [], resolver)
        self.assertIn("refused address", str(err.exception))

    def test_one_private_address_in_a_mixed_answer_refuses_the_whole_host(self):
        resolver = table_resolver({"careers.example.com": [PUBLIC, "10.0.0.5"]})
        with self.assertRaises(GuardError):
            robots_check.resolve_target("https://careers.example.com/job/1", [], resolver)

    def test_a_name_that_resolves_only_to_public_addresses_is_allowed_and_pinned_to_the_first(self):
        resolver = table_resolver({"careers.example.com": [PUBLIC, "8.8.8.8"]})
        target = robots_check.resolve_target("https://careers.example.com/job/1", [], resolver)
        self.assertEqual((target.host, target.port, target.ip), ("careers.example.com", 443, PUBLIC))

    def test_a_name_that_does_not_resolve_is_refused_not_a_traceback(self):
        resolver = table_resolver({})
        with self.assertRaises(GuardError) as err:
            robots_check.resolve_target("https://nowhere.example.com/", [], resolver)
        self.assertIn("does not resolve", str(err.exception))

    def test_an_ip_literal_is_checked_without_a_lookup(self):
        def no_lookup(host, port):
            raise AssertionError("an IP literal must not be resolved")
        with self.assertRaises(GuardError):
            robots_check.resolve_target(f"http://{METADATA}/latest/meta-data/", [], no_lookup)
        with self.assertRaises(GuardError):
            robots_check.resolve_target("http://[::1]:8080/x", [], no_lookup)
        target = robots_check.resolve_target("http://[2606:4700:4700::1111]/x", [], no_lookup)
        self.assertEqual(target.ip, "2606:4700:4700::1111")


# --- every hop, including redirects ----------------------------------------------------------------------------

class RedirectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = self.tmp / "page.html"
        self.table = {"jobs.example.com": [PUBLIC], "cdn.example.com": [PUBLIC],
                      "rebind.example.com": ["10.0.0.9"]}

    def fetch(self, url, hop, blocklist=()):
        return robots_check.guarded_fetch(url, self.out, ua="x", accept="*/*", blocklist=blocklist, hop=hop,
                                          resolver=table_resolver(self.table))

    def test_a_redirect_to_the_metadata_address_is_refused_and_never_requested(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (302, f"http://{METADATA}/latest/meta-data/iam/")})
        with self.assertRaises(GuardError) as err:
            self.fetch("https://jobs.example.com/job/1", hop)
        self.assertIn(METADATA, str(err.exception))
        self.assertEqual(hop.requested, ["https://jobs.example.com/job/1"], "the metadata URL must not be requested")

    def test_a_redirect_to_loopback_is_refused_where_it_happens(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (301, "http://127.0.0.1:8080/admin")})
        with self.assertRaises(GuardError):
            self.fetch("https://jobs.example.com/job/1", hop)
        self.assertEqual(len(hop.requested), 1)

    def test_a_relative_redirect_is_resolved_against_the_current_hop_and_checked(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (302, "/internal/../../admin"),
                           "https://jobs.example.com/admin": (302, "http://10.0.0.5/")})
        with self.assertRaises(GuardError):
            self.fetch("https://jobs.example.com/job/1", hop)
        self.assertEqual(hop.requested, ["https://jobs.example.com/job/1", "https://jobs.example.com/admin"])

    def test_a_redirect_into_a_name_that_resolves_private_is_refused(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (302, "https://rebind.example.com/x")})
        with self.assertRaises(GuardError):
            self.fetch("https://jobs.example.com/job/1", hop)
        self.assertEqual(len(hop.requested), 1, "the private name must not be requested")

    def test_a_redirect_to_a_blocklisted_host_is_refused_before_the_request(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (302, "https://www.linkedin.com/jobs/view/1")})
        with self.assertRaises(GuardError) as err:
            self.fetch("https://jobs.example.com/job/1", hop, blocklist=("linkedin.com",))
        self.assertIn("blocklist", str(err.exception))
        self.assertEqual(len(hop.requested), 1)

    def test_a_clean_chain_is_followed_and_each_hop_is_pinned_to_its_checked_address(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (302, "https://cdn.example.com/job/1")})
        code, size = self.fetch("https://jobs.example.com/job/1", hop)
        self.assertEqual(code, 200)
        self.assertEqual(hop.requested, ["https://jobs.example.com/job/1", "https://cdn.example.com/job/1"])
        self.assertEqual([t.ip for t in hop.targets], [PUBLIC, PUBLIC])

    def test_redirect_loops_stop_at_the_hop_limit(self):
        hop = HopRecorder({"https://jobs.example.com/a": (302, "https://jobs.example.com/b"),
                           "https://jobs.example.com/b": (302, "https://jobs.example.com/a")})
        with self.assertRaises(RuntimeError) as err:
            self.fetch("https://jobs.example.com/a", hop)
        self.assertIn("redirects", str(err.exception))
        self.assertLessEqual(len(hop.requested), robots_check.MAX_REDIRECTS + 1)


# --- the curl argv: the checked address is the one connected to -------------------------------------------------

class CurlArgvTests(unittest.TestCase):
    def test_fetch_page_never_lets_curl_follow_redirects(self):
        # curl -L would follow a redirect without a check. The guard follows them itself, one checked hop at a time.
        argv = fetch_page.build_curl_argv("https://jobs.example.com/job/1", Path("/tmp/x.html"))
        self.assertNotIn("-L", argv)
        self.assertNotIn("--location", argv)
        self.assertEqual(argv[-2:], ["--", "https://jobs.example.com/job/1"])

    def test_the_hop_connects_to_the_address_that_was_checked(self):
        target = robots_check.Target("jobs.example.com", 443, PUBLIC)
        argv = robots_check.hop_argv("https://jobs.example.com/job/1", Path("/tmp/x"), ua="x", accept="*/*",
                                     target=target)
        pin = argv[argv.index("--resolve") + 1]
        self.assertEqual(pin, f"jobs.example.com:443:{PUBLIC}")
        self.assertNotIn(METADATA, " ".join(argv))

    def test_an_ipv6_pin_is_written_in_brackets(self):
        target = robots_check.Target("ipv6.example.com", 443, "2606:4700:4700::1111")
        argv = robots_check.hop_argv("https://ipv6.example.com/x", Path("/tmp/x"), ua="x", accept="*/*", target=target)
        self.assertEqual(argv[argv.index("--resolve") + 1], "ipv6.example.com:443:[2606:4700:4700::1111]")


# --- the blocklist ----------------------------------------------------------------------------------------------

class BlocklistTests(unittest.TestCase):
    def test_linkedin_is_always_on_the_list_and_its_regional_hosts_are_covered(self):
        patterns = robots_check.load_blocklist(env={})
        for host in ("linkedin.com", "www.linkedin.com", "mx.linkedin.com", "br.linkedin.com", "co.linkedin.com"):
            with self.subTest(host=host):
                self.assertIsNotNone(robots_check.blocked_host(host, patterns), host)

    def test_a_look_alike_of_a_blocklisted_name_is_not_blocked_by_the_suffix_rule(self):
        patterns = robots_check.load_blocklist(env={})
        self.assertIsNone(robots_check.blocked_host("notlinkedin.com", patterns))
        self.assertIsNone(robots_check.blocked_host("linkedin.com.example", patterns))

    def test_jobs_blocklist_adds_hosts_from_the_environment_and_the_argument(self):
        patterns = robots_check.load_blocklist(["Careers.Example.org"],
                                               env={"JOBS_BLOCKLIST": "recruiter.example, *.spam.example"})
        self.assertIsNotNone(robots_check.blocked_host("jobs.recruiter.example", patterns))
        self.assertIsNotNone(robots_check.blocked_host("x.spam.example", patterns))
        self.assertIsNotNone(robots_check.blocked_host("careers.example.org", patterns))

    def test_a_blocklist_entry_that_is_not_a_host_is_refused(self):
        with self.assertRaises(ValueError):
            robots_check.load_blocklist(env={"JOBS_BLOCKLIST": "https://recruiter.example/path"})

    def test_a_blocklisted_host_is_refused_before_robots_or_any_request(self):
        with mock.patch.object(robots_check, "_fetch", side_effect=AssertionError("no request may be sent")):
            with mock.patch.object(robots_check, "resolve_host", side_effect=AssertionError("no lookup either")):
                rc, message = robots_check.gate("https://www.linkedin.com/jobs/view/4012345678/",
                                                robots_check.load_blocklist(env={}))
        self.assertEqual(rc, 1)
        self.assertIn("blocklist", message)

    def test_the_environment_list_reaches_gate_without_an_argument(self):
        with mock.patch.dict(os.environ, {"JOBS_BLOCKLIST": "recruiter.example"}):
            with mock.patch.object(robots_check, "_fetch", side_effect=AssertionError("no request")):
                rc, message = robots_check.gate("https://jobs.recruiter.example/job/1")
        self.assertEqual(rc, 1)
        self.assertIn("refused", message.lower())


# --- fetch_page end to end, with the hops faked -----------------------------------------------------------------------

POLICY = "User-agent: *\nAllow: /\n"


class FetchPageGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = self.tmp / "page.html"
        self.resolve = table_resolver({"jobs.example.com": [PUBLIC], "robots.example.com": [PUBLIC]})

    def run_main(self, hop, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        patches = [
            mock.patch.object(robots_check, "_fetch", return_value=(POLICY, 200)),
            mock.patch.object(robots_check, "curl_hop", hop),
            mock.patch.object(robots_check, "resolve_host", side_effect=self.resolve),
            mock.patch.object(fetch_page.shutil, "which", return_value="/usr/bin/curl"),
        ]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = fetch_page.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_a_redirect_to_the_metadata_address_exits_1_and_saves_nothing(self):
        hop = HopRecorder({"https://jobs.example.com/job/1": (302, f"http://{METADATA}/latest/meta-data/")})
        code, out, err = self.run_main(hop, "https://jobs.example.com/job/1", "--out", str(self.out))
        self.assertEqual(code, 1, err)
        self.assertIn("network guard", err)
        self.assertNotIn(f"http://{METADATA}/latest/meta-data/", hop.requested)
        self.assertFalse(self.out.exists())

    def test_a_linkedin_url_exits_1_and_no_request_is_sent(self):
        hop = HopRecorder()
        code, out, err = self.run_main(hop, "https://www.linkedin.com/jobs/view/4012345678/", "--out", str(self.out))
        self.assertEqual(code, 1)
        self.assertEqual(hop.requested, [])
        self.assertIn("blocklist", out + err)

    def test_a_host_named_in_jobs_blocklist_exits_1_and_no_request_is_sent(self):
        hop = HopRecorder()
        with mock.patch.dict(os.environ, {"JOBS_BLOCKLIST": "jobs.example.com"}):
            code, out, err = self.run_main(hop, "https://jobs.example.com/job/1", "--out", str(self.out))
        self.assertEqual(code, 1)
        self.assertEqual(hop.requested, [])

    def test_a_host_named_with_the_blocklist_argument_exits_1(self):
        hop = HopRecorder()
        code, _, err = self.run_main(hop, "https://jobs.example.com/job/1", "--out", str(self.out),
                                     "--blocklist", "jobs.example.com")
        self.assertEqual(code, 1)
        self.assertEqual(hop.requested, [])

    def test_a_clean_posting_is_fetched_and_saved(self):
        hop = HopRecorder()
        code, out, err = self.run_main(hop, "https://jobs.example.com/job/1", "--out", str(self.out), "--text")
        self.assertEqual(code, 0, err)
        self.assertIn("HTTP 200", out)
        self.assertTrue(self.out.is_file())


class FetchPageSubprocessTests(unittest.TestCase):
    """The real script, as a bot runs it. Every case is refused before a lookup, so no network is used."""

    def run_script(self, *args):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPTS / "fetch_page.py"), *args, "--out", str(Path(tmp) / "p.html")],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )

    def test_the_metadata_address_as_a_literal_exits_1(self):
        proc = self.run_script(f"http://{METADATA}/latest/meta-data/iam/security-credentials/")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("REFUSED", proc.stdout)

    def test_loopback_and_ipv6_loopback_literals_exit_1(self):
        for url in ("http://127.0.0.1:9/job", "http://[::1]:9/job", "http://10.0.0.5/job"):
            with self.subTest(url=url):
                proc = self.run_script(url)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("REFUSED", proc.stdout)

    def test_linkedin_and_a_regional_linkedin_host_exit_1(self):
        for url in ("https://www.linkedin.com/jobs/view/4012345678/", "https://mx.linkedin.com/jobs/view/1"):
            with self.subTest(url=url):
                proc = self.run_script(url)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("blocklist", proc.stdout)

    def test_a_non_http_scheme_still_exits_2(self):
        self.assertEqual(self.run_script("file:///etc/hosts").returncode, 2)


class RobotsCliTests(unittest.TestCase):
    def test_robots_check_refuses_the_metadata_literal_and_exits_1(self):
        proc = subprocess.run([sys.executable, "-I", str(SCRIPTS / "robots_check.py"),
                               f"http://{METADATA}/latest/meta-data/"],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("REFUSED", proc.stdout)

    def test_robots_check_accepts_a_blocklist_argument(self):
        proc = subprocess.run([sys.executable, "-I", str(SCRIPTS / "robots_check.py"),
                               "https://careers.example.org/job/1", "--blocklist", "careers.example.org"],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("blocklist", proc.stdout)


if __name__ == "__main__":
    unittest.main()

# Upstream watcher fixtures

Recorded 2026-10-15 from the live GitHub endpoints, used by `tests/test_watch_upstream.py`.

- `releases.json`: `GET https://api.github.com/repos/NousResearch/hermes-agent/releases?per_page=5`, unmodified (v0.22.1, v0.22.0, v0.21.7, v0.21.6, v2026.9.24). `releases.meta.json` holds the ETag of that response.
- `releases.atom.xml`: `https://github.com/NousResearch/hermes-agent/releases.atom`, trimmed to three entries (v0.22.1 with its body cut at ~24k chars, a `v0.22.0+canary.*` entry and `rc.5-v0.22.1`). The feed lists rc and canary tags that the API list does not.
- `release-v0.22.0.md`: body of the GitHub release v0.22.0, unmodified; the filter test checks section-scoped bullets (Kanban, Cron, Plugin system) survive the cap.
- `hermes-version.txt`: first line of `hermes --version` on the recording machine.

The docs signal tests build their own fake `website/docs` tree in a temp dir; no docs are recorded here.

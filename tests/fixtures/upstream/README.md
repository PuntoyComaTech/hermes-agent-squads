# Upstream watcher fixtures

Recorded 2026-10-15 from the live GitHub endpoints, used by `tests/test_watch_upstream.py`.

- `releases.json`: `GET https://api.github.com/repos/NousResearch/hermes-agent/releases?per_page=5`, unmodified (v0.22.1, v0.22.0, v0.21.7, v0.21.6, v2026.9.24). `releases.meta.json` holds the ETag of that response.
- `releases.atom.xml`: `https://github.com/NousResearch/hermes-agent/releases.atom`, trimmed to three entries (v0.22.1 with its body cut at ~24k chars, a `v0.22.0+canary.*` entry and `rc.5-v0.22.1`). The feed lists rc and canary tags that the API list does not.
- `hermes-version.txt`: first line of `hermes --version` on the recording machine.
- `squads-distribution.yaml`, `squads-changelog.md`: SYNTHETIC. `distribution.yaml` is not on main of the squads repo yet (404 at recording time).

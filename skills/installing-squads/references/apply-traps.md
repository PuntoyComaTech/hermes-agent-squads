# Install and apply traps

Each trap makes `apply` report success while the bot runs something other than
what the repository ships.

- `hermes profile install <dir>` refuses any folder that contains a symlink, and
  a `.venv` is one. Install from a snapshot of tracked files
  (`git ls-files -co --exclude-standard` into `rsync --files-from`), never from
  a working copy.
- `scripts/hpy` takes a bare script name (`model_advisor.py`), never a path: it
  prefixes its own scripts folder, so an absolute path is doubled and fails with
  file-not-found.
- An `env:<KEY>` row of `hermes auth list` is the CLI's own environment (the
  root env file); a bot run does not get that environment, so the row is not a
  credential the bot holds. Count a provider as held only from a stored source.
  Counting `env:` rows skips the copy, and the bot falls back with a primary
  auth failure.
- A mirrored setting the user's root config would put back is fixed in
  `squadctl`, not in the installed config: `apply` re-copies the user's values
  on every run, so a hand-edited bot config is undone at the next apply. Add the
  exclusion in the generator with a test that goes red when it is removed
  (`skills/changing-bots`).

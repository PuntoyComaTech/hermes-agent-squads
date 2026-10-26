# Reviewing a change the builder made to the squad

When the user says "I just made an adjustment for X" (a bot, a skill, a stage, a portal), they are asking whether it
actually works, not for a description of it. Deliver a verdict per claim, with the failing cases named and evidenced by
exit codes. Never edit the files of another bot in this chat: the fix list goes back to the builder.

## Procedure

1. **Both copies.** The source of truth is `~/.hermes/profiles/builder/squads/<squad>/` (skills, `squad.yaml`
   version, `README.md`); each bot holds the installed copy at
   `~/.hermes/profiles/<bot>/skills/squad-jobs/<skill>/`. `diff -rq` them — a `.squad-sha` file in the installed copy
   is expected and is not a difference. Reviewing the source alone leaves the outdated installed copy unmeasured.
2. **Read, then compile.** The changed `SKILL.md`, every reference it names, then the scripts in `scripts/`:
   `python3 -m py_compile` each and run `--help` on it, since these scripts carry their input format in the docstring
   and the help text is where a format rule is stated.
3. **Real data, then adversarial fixtures.** First run the scripts against the project's own files (`profiles/*.json`,
   `documents/<platform>/*.json`, the newest market file). Then write fixtures in
   `$HERMES_HOME/cache/scratch`: inverted `from`/`to` dates, a field left unchanged, an already-deleted row, a path
   traversal and an encoded traversal in any URL guard, `http`, and a lookalike domain. A guard that passes only its
   happy path is untested.
4. **Grep the tree for the OLD behaviour's vocabulary.** `evals/`, `references/` and script docstrings reliably keep
   the prior affordance ("the user pastes the text", "titles and dates stay the user's") after a feature flips to the
   bot doing that work. The bot follows the stale line and blocks on a step that no longer exists — a contradiction
   between two files of one skill is a defect, not a wording preference.
5. **Report** in `user_language`, as an ordered punch list: what works with the evidence (cases tried, exit codes),
   then the failures ranked by what breaks a run, then the scope gaps against what the user said they wanted, then
   one line of context on anything that looks broken but is only state (a capture taken before the fix, work not yet
   run). No file edits, no builder commands run from here.

## Where a green check lies

- **Prose guard vs code guard.** A rule written only in the SKILL text ("never change the photo") leaves the URL
  allow-list in the script permitting those pages. Read the allow/deny list before trusting the rule; a rule that only
  prose enforces is a finding in the report.
- **Existence asserted instead of content.** A structure check that reports ok because the row exists does not prove
  the name changed — an edit row with a `was` value needs the old name to be *absent* afterwards.
- **Substring matching.** Date tokens compared as substrings pass both ways: a bare year matches inside a month-year,
  and an inverted `from`/`to` order matches too. Require order, or state that the token is matched loosely.
- **An edit path that is only prose.** A read-only, measured selector reference is not an edit procedure. When a
  feature depends on typing into a form, driving date selects, creating or deleting an entry, and the skill leaves it
  as a sentence, name that gap first: every run after it improvises those clicks.

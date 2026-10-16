# Squad: Marketing

A manager and four workers that run a brand's marketing cycle: onboarding, a 90-day plan, a weekly calendar, reviewed pieces and a monthly report. Every card goes on the `marketing` board; the user approves, requests changes or discards from the manager's chat. The squad never publishes, sends, schedules or spends without the user's explicit OK for that action.

Bots, lanes, skills, keeps, crons and the `piece` chain: `squad.yaml`. Only the visible manager (`marketing`) talks to the user. File layout, card fields, keys and rules: skill `brand-contract`. Licences: [skills/LICENSES.md](skills/LICENSES.md).

## The piece chain

`research` (only when the brief says `Needs research: yes`) -> `copy` -> `asset` -> `review` -> `approve`.

- The reviewer returns `approve`, `fix` (up to `brand.md -> reviewer_rounds` rounds, then a re-review of the same card) or `escalate`.
- The manager presents an approved piece; a change request starts a `-c<N>` round with the user's literal wording. Every reply is logged in `preferences.md`.
- A `publish` card exists only when `brand.md -> publishing` names a connector and the user confirmed that piece.

The user can file a chain by hand:

```sh
scripts/squadctl chain marketing piece --project <slug> --title "<piece title>" --run-id <piece-id> [--when research]
```

## Crons

`marketing-plan-week` (Mondays) files one calendar card per active brand without next week's calendar. `marketing-report` (the 1st) files one report card per active brand whose `data/inbox/` changed. Both print nothing on success and skip brands with a `PAUSE` file.

## Install

```sh
scripts/squadctl plan marketing
scripts/hpy model_advisor.py marketing --json > models.json
scripts/squadctl apply marketing --models models.json
scripts/squadctl project add marketing "<Brand>" <path>
```

One brand is one Hermes Project. `brand.md` stays `draft` until the user approves onboarding; only `active` brands get calendars and reports.

## Scope

Not included: publishing, sending, scheduling or ad spend (the user does it); full websites (web squad); long video or 3D (studio squad). Ad accounts, pixels and connectors are added per brand.

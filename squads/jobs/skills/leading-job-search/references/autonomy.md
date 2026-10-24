# Autonomy and confidentiality

The user wants the squad to move on its own, and to keep their employer's work private.

## Contents

- What needs the user, and what does not
- Confidential work
- Eligibility before a writer card

## What needs the user, and what does not

The user wants the squad to move on its own. Ask only for these, and never twice for the same thing:

- a fact you do not have (a date, a tool used, a degree name): ask once, in one line, all the questions together.
  First search every file the user wrote (`achievements.yaml`, `profile.md`, `application-data.yaml`,
  `documents/cv/`, your memory): a fact in any of them is known. Copy it into `achievements.yaml` and say so after;
  never ask it. A detail no document claims (which vector store) is never asked: it is interview preparation;
- `apply` for one opening (or the screenshot under `auto_apply: ask`), and anything else that contacts a third party;
- a public write: the LinkedIn fields, once, on the final text;
- the `RESET` word, a paid action, a credential.

Everything else runs without a question and is reported after, in one line each: re-analysing or rewriting after a
profile change, a CHANGE round the user asked for in other words, correcting a document, filing the next card,
archiving a superseded draft, fixing a validation finding with facts already given. A correction the user gives
("not 7 to 10 people", "do not name the clients") is the approval: apply it to `achievements.yaml`, `profile.md` and
every open document in the same turn, then say what changed. Never ask "should I continue?" or "ok?" after the user
said what they want.

## Confidential work

Two lists, two scopes. `keep_off_public_profile` holds what a CV, letter or form answer sent to one employer may say
but a public profile may not (clients of the current employer, team size): only the LinkedIn copy checker refuses it.
`profile.md` `confidential_terms` lists what never leaves the project: client and brand names of the current employer,
internal project names, team size when the user asks so, a second job. The renderer, the profile checker, the review
and the submit gate refuse any of them in a CV, letter, form answer, recruiter message or public profile. When the user
says something is confidential, ask nothing: put the names in the list whose scope they gave ("not on LinkedIn" ->
`keep_off_public_profile`, "never" -> `confidential_terms`) at once (that is their instruction, no "ok"
needed), describe the work by sector and scope ("e-commerce for global brands in Brazil and LATAM"), and file CHANGE
cards for every open application that names them. Internal reasoning files (`strategy.md`, `analysis.json`) may keep
the names; nothing outward does.

## Eligibility before a writer card

A jobs-writer card for an opening is filed only when its eligibility gate is PASS, or the user accepted the risk.

- PASS: file it.
- FLAG: say the eligibility note from `analysis.json` in one line and ask: "Eligibility is unclear: <note>. Write
  anyway, or skip?". File the card only after a yes, and its body then carries `Eligibility risk accepted by the user
  (<date>)`. A FLAG is resolved when the user gives the fact (a permit, a residency) and `eligibility` in `profile.md`
  is updated after their ok.
- DISCARD: file nothing; say why in one line.

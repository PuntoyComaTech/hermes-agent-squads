# Data and auth

## Migrations

- One migration per change, numbered and forward-only; never edit one applied on a deployed environment.
- A migration that drops or rewrites a column, table or rows is destructive: mark it `destructive: yes` with its rollback in the milestone note. web-deployer runs it only after a backup and a `Confirmed:` line.

## Auth

- Sessions and password hashing use the platform's primitive, never hand-rolled.
- Rate-limit the endpoints an anonymous user can reach (login, signup, contact, password reset).

## Integrations and secrets

- Third-party calls happen on the server; the client never receives an API key.
- Secrets and bindings: names in the milestone note, values from the deployer's environment. Never in the repo, a committed `.env`, a fixture, a log or an error message.
- Data deletion: when the spec promises a deletion path, it deletes the record and its derived data, and the test proves it.

## Verification

- The failure paths are tested: invalid input, unauthorized access, missing record, duplicate submit.
- No secret appears in `git log`, in the bundle, or in the test output.

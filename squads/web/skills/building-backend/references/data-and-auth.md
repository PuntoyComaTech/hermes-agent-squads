# Data and auth

Squad decisions only; standard practice is assumed.

## Migrations

- One migration per change, numbered and forward-only; never edit one already applied on a deployed environment.
- A migration that drops a column, table or row range is destructive: it needs a backup first and the user's confirmation before it runs in production.
- Test the migration twice: on a fresh database and on a copy of the current one. Record the rollback in the milestone note.

## Auth

- Sessions and password hashing use the platform's primitive, nothing hand-rolled.
- Rate-limit the endpoints an anonymous user can reach (login, signup, contact, password reset).

## Integrations and secrets

- Third-party calls happen on the server; the client never receives an API key.
- Secrets and bindings: named in the milestone note, provided by the environment. Never in the repo, in fixtures, in logs, or in an error message.
- Data deletion: when the spec promises a deletion path, it deletes the record and its derived data, and the test proves it.

## Verification

- The failure paths are tested: invalid input, unauthorized access, missing record, duplicate submit.
- No secret appears in `git log`, in the bundle, or in the test output.
- Every destructive migration has its backup and its confirmation requirement recorded.

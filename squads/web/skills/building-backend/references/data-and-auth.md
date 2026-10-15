# Data and auth

## Data model

- Model the domain in nouns the user would recognize; store what the site must retrieve, not what is convenient today.
- Every table: a stable primary key, `created_at`, and `updated_at` when it mutates. No natural keys as primary keys.
- Constraints live in the schema (not null, unique, foreign keys, check), not only in application code.
- Denormalize only with a measured reason; record it in `decisions.md`.
- Names: `snake_case` for SQL, `camelCase` for the API payloads. One convention per layer.

## Migrations

- One migration per change, numbered and forward-only; never edit a migration already applied on a deployed environment.
- A migration that drops a column, table or row range is destructive: it needs a backup first and the user's confirmation before it runs in production.
- Test the migration twice: on a fresh database and on a copy of the current one.
- Rollback story per migration: reversible (a new migration), or documented as irreversible with the backup path.

## Auth

- Passwords: the platform primitive (`scrypt`, `argon2`, or the framework's helper), never a hand-rolled hash, never a fast general-purpose hash.
- Sessions: httpOnly, secure, sameSite cookie with an expiry; rotate the session id on login and privilege change.
- Tokens: short-lived access, rotating refresh; never a token in `localStorage` when a cookie will do.
- Authorization is checked on the server for every protected route, per resource: never trust a client-side flag.
- Enumeration: login and recovery answer the same way whether or not the account exists.
- Rate-limit the endpoints an anonymous user can reach (login, signup, contact, password reset).
- Logout invalidates the session server-side, not only the cookie.

## API surface

- REST: nouns for resources, verbs for actions that are not CRUD; predictable status codes (200/201/204, 400/401/403/404/409/422, 429, 500).
- Validate input at the boundary with one schema shared by handler and tests.
- Errors: a stable machine code plus a human message; never a stack trace, an SQL fragment or a vendor message.
- Paginate every list; cap the page size server-side.
- Idempotency for anything a user can submit twice (order, signup, form) via a key, not a time window.

## Integrations and secrets

- Third-party calls happen on the server; the client never receives an API key.
- Timeout and retry every outbound call (bounded retries, jitter); fail closed on the site's critical path and degrade gracefully elsewhere.
- Validate the webhook signature before trusting a payload.
- Secrets and bindings: named in the milestone note, provided by the environment. Never in the repo, in fixtures, in logs, or in an error message.
- Data deletion: when the spec promises a deletion path, it deletes the record and its derived data, and the test proves it.

## Verification

- The failure paths are tested: invalid input, unauthorized access, missing record, duplicate submit.
- A fresh checkout can run the suite with only the names from the milestone note.
- No secret appears in `git log`, in the bundle, or in the test output.
- Every destructive migration has its backup and its confirmation requirement recorded.

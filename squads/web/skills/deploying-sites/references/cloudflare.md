# Cloudflare deploys

`cf` does everything: projects, builds, deploys, versions, DNS, domains, D1, R2, KV. It is in open beta, so every command is confirmed with `cf cli search "<task>"` before use, the shapes below are what to look for, not a substitute for the search.

## Auth

- Token from the profile's passthrough: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
- Named login per client or per wall, when `site.yaml` sets one: `cf auth create <name>`, `cf auth activate <name>`, `cf auth whoami`, `cf auth list`, `cf auth deactivate`, `cf auth delete`.
- Precedence between the environment token and a named profile is undocumented, so never rely on it: for a site with a named login, run every command as

```bash
env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID cf --profile <name> <command>
```

and confirm the account with `cf auth whoami` before the first deploy.

## Preview and production

- Preview: upload a version from the branch without making it live (`cf workers versions create` or the project's deploy-without-promote form). The preview URL goes in the deploy record.
- Production: deploy `main` (or promote the uploaded version) and record the previous `version_id` first, it is the rollback target.
- Rollback: bring the previous `version_id` back, then `git revert` the merge.
- List versions and deployments before and after, so the record matches reality.
- A Wrangler-configured template (a Next.js or TanStack project scaffolded with Wrangler files) needs `cf migrate --dry-run`, then `cf migrate`, before any `cf dev`, `cf build` or `cf deploy`.
- A Worker's custom domain has no direct command in some builds: declare it in the project config and apply it with the triggers command (`cf workers triggers deploy`), running `--dry-run` first for the DOMAIN CHECK phase.

## DNS and domains

- Read first: the zone, its nameservers, and the records that will change. Write them into the card before asking for the user's yes.
- Apply only with the `Confirmed:` line: the site's record, or the nameserver move when the domain is not on Cloudflare yet.
- Verify with a DNS lookup and an HTTPS request before completing.

## Data (only when the spec needs it)

- D1: `cf d1 migrations apply` on the deploy stage, never from a build card. Export a backup before a destructive migration with the export command from `cf cli search "d1 export"`.
- R2 and KV: created once at onboarding, bound to the Worker; names recorded in the milestone note, values never.
- The token needs the matching permission before these exist; a missing permission is a one-line request to the user, not a different approach.

## Wrangler exceptions

Only two, and only after `cf cli search` shows there is no `cf` way: setting one secret (`npx wrangler secret put <NAME> --name <worker>`, or a secrets file on a version create) and live logs (`npx wrangler tail <worker>`). Wrangler does not read `cf` profiles: at a site with a named login, block until the client's own access for these two is arranged.

## Vercel sites

Only when `site.yaml -> provider: vercel`: token in the deployer's environment, one preview per branch, promote for production, rollback to the previous deployment, domains through the dashboard or CLI. A commercial site never runs on Vercel Hobby; check before the first production deploy.

## Never

- Never edit DNS without the `Confirmed:` line; never delete a zone or record.
- Never deploy a branch other than the reviewed one, and never without the `Confirmed:` line for production.
- Never print the token or paste it into a file, a card or a command that echoes.

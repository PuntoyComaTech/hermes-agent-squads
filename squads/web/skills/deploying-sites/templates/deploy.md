# deploy.md — <project>

One per project, in the project folder beside `site.yaml`. `deploying-sites` refuses to deploy
without it (skill step 3). Fill every field with the real values; never leave a placeholder.

- target: <provider and service, e.g. "Cloudflare Pages project acme-web, production branch main">
- command: <the exact build + deploy command, e.g. "pnpm build && cf pages deploy dist --project acme-web">
- env names: <environment variable NAMES the command needs — never values, e.g. "GH_TOKEN, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID">
- rollback: <how to restore the previous version, e.g. "cf pages deployment restore <previous_version_id>, then git revert the merge on main">

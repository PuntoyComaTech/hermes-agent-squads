# deploy.md — <project>

One per project, in the project folder beside `site.yaml`. `deploying-sites` refuses to deploy
without it (skill step 3). Fill every field with the real values; never leave a placeholder.

- target: <provider and service, e.g. "Cloudflare Pages project acme-web, production branch main">
- command: <the exact build + deploy command, e.g. "pnpm build && cf pages deploy dist">
- creds: <the logins the command runs on, by name — e.g. "gh (repo scope), cf named login acme" — and any
  environment variable NAMES it needs; never a value, never a token>
- rollback: <how to restore the previous version, e.g. "cf pages deployments rollback <previous_version_id>,
  then git revert the merge on main">

# GitHub flow

Auth is only `GH_TOKEN` (fine-grained personal access token) through the profile's passthrough. Never `gh auth login`.

## Check the token before anything

```bash
gh auth status                          # the token user
gh api user --jq .login                 # who it is
gh api user/repos --paginate --jq '.[].full_name'   # which repos it sees
```

Whether it can create repositories, without creating one:

```bash
gh api -X POST user/repos -f name= 2>&1 | tail -1   # HTTP 422: it can; HTTP 403 or anything else: it cannot
```

## Repo modes

- `bot_creates` (token sees all repositories plus Administration write): create the private repo, set `origin`, push `main`.
- `user_creates` (token sees only the site repos): verify the user's empty private repo is reachable, then push. Not reachable -> block with click-by-click steps: create an empty private repo named `<slug>`, add it to the token's repository access, reply "done".

```bash
gh repo create <owner>/<slug> --private --source repo --remote origin --push   # bot_creates
gh repo view <owner>/<slug> --json name,visibility,isEmpty                      # user_creates
```

Then set `site.yaml -> repo.mode` and `repo.created: true`.

## Branches and pull requests

- One branch per work item: `web/<ID>`, pushed from the site's `repo/`.
- Authenticate pushes per repository, never globally:

```bash
git -C repo config credential.helper '!gh auth git-credential'
git -C repo push -u origin web/<ID>
```

- One PR per work item, updated on each new push; title from the milestone, body with the summary, the preview URL and the acceptance criteria.

```bash
gh pr create --repo <owner>/<slug> --base main --head web/<ID> --title "<milestone>" --body-file -
gh pr view <n> --repo <owner>/<slug> --json number,url,mergeStateStatus,statusCheckRollup
```

## Merging and rollback

```bash
gh pr merge <n> --repo <owner>/<slug> --merge          # merge commit: never --squash, never --rebase
git -C repo revert -m 1 <merge-commit> && git -C repo push origin main   # rollback after the provider step
```

Stacked milestones merge in order. A conflicted PR: file a card for the bot that built it (deploying-sites step 9), never a force push.

## Rules

- Never `git push --force` or `-f`; never rewrite a published branch.
- Never `gh repo delete`, `gh repo archive`, or change repository visibility, collaborators or settings.
- Never commit to `main` directly; `main` only advances through merges and reverts.
- Secrets never enter a branch, a PR body, a commit message or an issue.

# Removing personal data from published history

Run this only with the user's explicit OK for the rewrite and for the
force-push. Read it whole before the first command.

1. Build the term list outside the repository: names, handles, personal email
   addresses, employers, project and client names, profile URLs. Include every
   commit author and committer address, but keeping the account address the
   commit history already publishes is the user's decision: rewritten authors
   make ordinary pull requests look odd. Rewrite only the addresses the user
   approves, and map an author either to their real address or leave it, never
   to an invented one.
2. Back up first: `git bundle create <scratch>/backup.bundle --all`, then
   mirror-clone the remote into a scratch folder. Never rewrite the working
   checkout.
3. Rewrite with
   `git filter-repo --force --mailmap <map> --replace-text <rules> --replace-message <rules>`.
   The mailmap covers author and committer; `--replace-message` covers commit
   messages, which keep names after a tree-only fix. Replace each term with
   neutral wording, never an invented brand, a placeholder person or
   `[REDACTED]`, and reword the whole sentence: a leftover fragment (a lone
   "example" or half a name) reads as residue.
4. Check the tree before anything else: when only identities and messages
   changed, `git rev-parse HEAD^{tree}` equals the pre-rewrite tree. A
   different tree means the rewrite changed content; stop and review.
5. Scan the rewritten history: `git log --all -p` for every term, and
   `git log --all --format='%ae %ce'` for the address set. Both must be empty
   except the platform noreply addresses.
6. Force-push with an explicit lease: read the old hash with
   `git ls-remote origin main`, then
   `git push --force-with-lease=main:<old-sha> origin main`. When the push asks
   for a username, use `git -c credential.helper='!gh auth git-credential' push`.
7. Re-sync each local clone to the new base only when its tree matches
   (`git reset --soft origin/main`, then confirm `git status` is unchanged).
   Delete local branches whose history is the old one, after confirming their
   tree is in `origin/main`. Then `git reflog expire --expire=now --all &&
   git gc --prune=now`.
8. Verify from a fresh clone: rerun the scan of step 5, and install from the
   repository URL into an empty `HERMES_HOME`.
9. Tell the user what survives. Pull-request refs (`refs/pull/*`) and cached
   old commits keep the old history and no push removes them:
   `git ls-remote origin 'refs/pull/*'` lists them. Removal needs a hosting
   support ticket with the old hashes, or recreating the repository (which
   loses stars, pull requests and links). Offer both.

# Protected facts and promotions

Below the front matter, free notes hold the constraints no key carries. Names that must never leave the project go
into `confidential_terms`; names a CV sent to one employer may carry but a public profile may not (clients of the
current employer, team size) go into `keep_off_public_profile`. The scripts enforce both. A protected fact that is not a name is a note line starting
`CONFIDENTIAL:` with the questions it covers:

```markdown
- CONFIDENTIAL: never state that the user holds another engagement in parallel. Questions on exclusivity or other
  employment are left empty: stop and ask the user.
```

Write the prohibition and its scope, never the reasoning, so a leaked document cannot state the fact.

A promotion inside one employer is two `experiences` entries that share the company: the earlier title closed on the
month it changed, the new one from that month. Never overwrite the old title.

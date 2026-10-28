# Codes a form mails after Submit

Greenhouse (and other ATSs) may answer Submit with "enter the security code sent to your e-mail to confirm you are a
human": an 8-character code of letters and digits, mailed from `greenhouse-mail.io`, single use and valid for about
10 minutes. It is not a CAPTCHA: the code sits in the user's mailbox, which jobs-inbox reads (triaging-inbox,
`Mode: CODE`). A kit at this point throws away an approved application.

1. Leave the form open, on the code field. Do not reload.
2. `python3 "$S/code_wait.py" --project <P> --opening <ID> --site greenhouse-mail.io --json` (another ATS: the
   sender's domain the form names). It checks that jobs-inbox is installed with its mail connected, files the
   `Mode: CODE` card (key `jobs:code:<ID>:<attempt>`) and waits up to 8 minutes for its result.
3. Its `outcome`:
   - `code` (or a `link`): type the code (open the link in the same tab) and submit. It is the same submit the gate
     opened: no second gate.
   - `no_code`: request a new code on the form once, then run step 2 with `--attempt 2`.
   - `unavailable`, `timeout`, or `no_code` on attempt 2: NOT_POSSIBLE with the kit. `submission.json` records
     `code_request: {card, outcome}` and the reason quotes code_wait's reason (unconnected mail says so; the user
     asks the manager "connect my mail"). check_submission.py refuses a NOT_POSSIBLE whose reason names
     an e-mailed code without this record.
4. The code never goes into a file, a note, a comment or memory: it lives in the jobs-inbox card result and in
   code_wait's output only.

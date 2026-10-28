# Connecting mail

jobs-inbox reads job mail over IMAP, read-only. The account is set once, without a terminal for the user.

1. Tell the user: a dialog asks for the Gmail address, Google's App passwords page opens in their browser (2-step
   verification must be on), and a hidden dialog takes the 16 letters. jobs-inbox only reads mail.
2. Run, with the terminal timeout at 900 (the user is typing in the dialogs):
   `I="$(dirname "$HERMES_HOME")/jobs-inbox"; HERMES_HOME="$I" python3 "$I/skills/squad-jobs/triaging-inbox/scripts/mail.py" setup --json`
3. `"login": "ok"`: mail is connected; the password is in the macOS Keychain, nowhere else. Unblock the inbox card
   that asked for it. An `error`: quote it; a refused password means a new app password, then run step 2 again.

Never ask for the password in chat, never type it, never read the Keychain.

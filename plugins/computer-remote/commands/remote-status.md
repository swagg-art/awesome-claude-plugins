---
description: Check the computer-remote agent - backend, screen size, missing tools, read-only state
argument-hint: "[host]"
allowed-tools: Bash(remotectl:*), Bash(python3:*)
---

Check whether the remote desktop agent is reachable and usable.

Host: `$1` (if empty, use the default target — `COMPUTER_REMOTE_URL`/token, or
the single entry in `~/.config/computer-remote/hosts.json` if there is only one).

1. Run `remotectl${1:+ --host $1} health`.
2. Report, in a few lines: the backend, screen size, whether it is read-only,
   and any `missing_tools`.
3. If it fails, name the likely cause and the fix — tunnel down, agent not
   running, token mismatch, missing platform tool. Do not retry blindly; see
   the `computer-remote` skill's `reference/troubleshooting.md`.

Do not send any input to the machine for this command.

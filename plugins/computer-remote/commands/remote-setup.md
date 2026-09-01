---
description: Walk through installing and starting the computer-remote agent on a target machine
argument-hint: "[macos|linux|windows]"
allowed-tools: Bash(python3:*), Read
---

Help the user get the computer-remote agent running on their target machine.

Target platform: `$1` (ask if not given).

Read `reference/setup.md` from the `computer-remote` skill and walk the user
through it for their platform, in this order:

1. Platform tools to install (and the exact install command).
2. `python3 remote_agentd.py --check` on the target to verify the backend.
3. Generating a token and locking it down to mode 600.
4. Starting the agent — mention `--read-only` as the safer option if they only
   want to look at the machine.
5. The SSH tunnel command, and the `~/.config/computer-remote/hosts.json` entry.
6. `remotectl --host NAME health` as the final check.

On macOS, call out the Accessibility and Screen Recording permissions
explicitly — input fails silently without them.

You are running on the controlling machine, not the target, so the user has to
run the target-side steps themselves. Give them exact commands to paste and
wait for the result at each step rather than dumping the whole list at once.

# Project summary — computer-remote plugin

**Repository:** swagg-art/awesome-claude-plugins
**Branch:** `claude/computer-remote-7bgr8a`
**Date:** 2026-09-01
**Scope agreed with the user:** a Claude Code plugin for *desktop* remote control
(screen + keyboard + mouse via an agent on the target machine), packaged as
`plugins/computer-remote/` without disturbing the existing UI or the generated
root README.

## What was built

A self-contained plugin in `plugins/computer-remote/`:

| Component | File | Notes |
|---|---|---|
| Agent daemon | `scripts/remote_agentd.py` | ~700 lines, stdlib only. JSON/HTTP on loopback, bearer-token auth, four platform backends. |
| Client CLI | `scripts/remotectl` | 11 subcommands, named hosts, actionable error messages. |
| Skill | `skills/computer-remote/SKILL.md` | The observe→act→observe loop, key syntax, batching, safety rules. |
| References | `skills/computer-remote/reference/{setup,protocol,troubleshooting}.md` | Per-platform install, full HTTP API, failure catalogue. |
| Commands | `commands/remote-{status,screenshot,do,setup}.md` | Read-only ones are scoped so they cannot send input. |
| Tests | `tests/test_agent.py` | 25 stdlib tests, no desktop or network needed. |
| Manifest / config | `.claude-plugin/plugin.json`, `config/hosts.example.json` | |
| CI | `.github/workflows/ci.yml` | New `plugins` job runs the Python tests; the existing `app` job is untouched. |

## Architecture

```
Claude Code ──▶ remotectl ──▶ ssh -L tunnel ──▶ remote_agentd.py ──▶ desktop
```

The daemon shells out to each platform's native tooling rather than depending on
pyautogui, so installation is "apt install two packages" instead of a Python
build toolchain. Backends are selected at startup and each declares the tools it
needs, so `--check` reports what is missing before anything fails mid-task.

| Platform | Screenshots | Input | Clipboard |
|---|---|---|---|
| Linux / X11 | imagemagick, scrot | xdotool | xclip, xsel |
| Linux / Wayland | grim | ydotool | wl-clipboard |
| macOS | screencapture | cliclick + osascript | pbcopy/pbpaste |
| Windows | PowerShell + .NET | SendKeys + user32 | Get/Set-Clipboard |

Key combos are written once in a normalised syntax (`ctrl+shift+t`, `cmd+space`,
`alt+f4`) and translated per backend, so a skill or script is portable.

## Security decisions

- **Loopback by default**, reached over an SSH tunnel. A non-loopback `--bind`
  is allowed but prints a warning explaining the exposure.
- **Bearer token on every request**, compared with `hmac.compare_digest`; the
  daemon refuses to start on a token under 16 characters.
- **`--read-only` mode** serves screenshots and returns 403 for all input,
  including clipboard writes — verified by tests.
- **Bounded requests**: 64 actions per batch, 4 MiB bodies, 30 s per tool call,
  click counts 1–5, sleeps capped at 5 s.
- **Skill-level rules**: confirm before destructive clicks, prefer `--region`
  over full-screen captures, never type credentials, hand control back at login
  prompts.

## Verification

- `python3 -m unittest discover -s tests` — **25 passed**. Covers key/region
  parsing, action dispatch ordering, drag press/release sequencing, auth (missing
  and wrong token → 401), read-only enforcement → 403, unknown route → 404,
  malformed JSON → 400, oversized batches → 400, PNG content type, clipboard
  round trip.
- Live client↔daemon round trip on an ephemeral port: `health` returned the
  backend and correctly flagged the missing `xdotool` in this headless
  container; bad token, read-only refusal, and connection-refused paths all
  produced the intended messages and exit code 1.
- `remote_agentd.py --check` exits non-zero when platform tools are missing.
- CI YAML and both JSON files parse.

## Known limits

- Only the primary display is captured and addressed; secondary monitors are
  reachable by coordinate on X11/Windows but not visible in screenshots.
- HiDPI needs a calibration click — the skill and troubleshooting doc both say
  so, since points-vs-pixels is the most common cause of misplaced clicks.
- macOS: no middle click, no horizontal scroll; Windows: no `meta`/Win key
  through SendKeys. Each returns a 501 naming the limitation rather than failing
  silently.
- Wayland input requires the `ydotool` daemon and `/dev/uinput` access;
  `--read-only` is the fallback.
- One controller at a time — the server is threaded, the desktop is not.

## Not done, deliberately

No root `.claude-plugin/marketplace.json`. The user chose plain in-repo
packaging, and adding one would change how the whole repository is published;
the plugin README says exactly what to add if that changes.

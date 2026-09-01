# computer-remote

Control another computer's desktop from Claude Code — screenshots, mouse,
keyboard, clipboard — over an SSH tunnel.

```
Claude Code ──▶ remotectl ──▶ ssh -L tunnel ──▶ remote_agentd.py ──▶ desktop
```

A small daemon runs on the machine you want to drive and exposes a JSON/HTTP API
on loopback. `remotectl` on the Claude side talks to it. Python 3.9+ on both
ends and nothing else — no pip install, no pyautogui; the agent shells out to
the platform's own tools.

## What's in the box

| Path | What it is |
|---|---|
| `scripts/remote_agentd.py` | The agent. Runs on the machine being controlled. |
| `scripts/remotectl` | The client CLI. Runs where Claude Code runs. |
| `skills/computer-remote/` | The skill Claude follows, plus setup, protocol and troubleshooting references. |
| `commands/` | `/remote-status`, `/remote-screenshot`, `/remote-do`, `/remote-setup` |
| `config/hosts.example.json` | Template for `~/.config/computer-remote/hosts.json` |
| `tests/test_agent.py` | Stdlib test suite for the agent. |

## Quick start

On the **target** machine:

```bash
sudo apt install xdotool imagemagick xclip          # Linux/X11; see setup.md for macOS/Windows
python3 remote_agentd.py --check                    # confirm the backend is usable
mkdir -p ~/.config/computer-remote
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > ~/.config/computer-remote/token
chmod 600 ~/.config/computer-remote/token
python3 remote_agentd.py                            # or --read-only for screenshots only
```

On the **controlling** machine:

```bash
ssh -N -L 8765:127.0.0.1:8765 me@target &
cp config/hosts.example.json ~/.config/computer-remote/hosts.json   # then edit it
chmod 600 ~/.config/computer-remote/hosts.json
remotectl --host laptop health
```

Then ask Claude to look at or drive the machine, or use `/remote-screenshot`
and `/remote-do`.

## Platform support

| Platform | Screenshots | Input | Clipboard |
|---|---|---|---|
| Linux / X11 | imagemagick or scrot | xdotool | xclip / xsel |
| Linux / Wayland | grim | ydotool | wl-clipboard |
| macOS | built in | cliclick | built in |
| Windows | built in | built in | built in |

macOS needs **Accessibility** and **Screen Recording** granted to whatever
launches the agent, or input is dropped and screenshots come back empty.

## Security

- Loopback-only by default, reached over SSH. A non-loopback `--bind` prints a
  warning: anyone who reaches the port and guesses the token owns the desktop.
- Every request needs a bearer token, compared in constant time.
- `--read-only` serves screenshots and refuses all input.
- Batches are bounded (64 actions, 4 MiB bodies, 30 s per tool call) so a
  runaway request cannot hold the desktop hostage.
- Screenshots capture whatever is on screen, including anything private. The
  skill tells Claude to prefer `--region`, and to ask before destructive clicks.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

25 tests covering key parsing, action dispatch, auth, error mapping and
read-only enforcement. No network access or desktop required — the HTTP layer
is exercised against a fake backend on an ephemeral port.

## Installing

This directory is a self-contained Claude Code plugin. Point Claude Code at it
directly:

```
/plugin install ./plugins/computer-remote
```

To make it installable by name from a clone of this repo, add a root
`.claude-plugin/marketplace.json` listing `plugins/computer-remote` — that is
deliberately not committed here, so this plugin does not change how the rest of
the repository is published.

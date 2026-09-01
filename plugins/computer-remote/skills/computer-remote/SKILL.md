---
name: computer-remote
description: Control a remote computer's desktop - take screenshots, move and click the mouse, type text and key combos, and read or write the clipboard - through the computer-remote agent daemon over an SSH tunnel. Use when the user asks to see, drive, click, type on, or automate a GUI on another machine (their laptop, a lab box, a VM, a kiosk), or mentions remotectl, remote_agentd, or a remote desktop session.
---

# Computer remote

Drive another machine's desktop from here. A small daemon (`remote_agentd.py`)
runs on the target machine and exposes screenshots and input over loopback HTTP;
`remotectl` on this machine talks to it, normally through an SSH tunnel.

```
Claude (here) ──▶ remotectl ──▶ ssh -L tunnel ──▶ remote_agentd.py ──▶ desktop
```

## Before anything else

Run `remotectl health` and read the answer. It tells you the backend
(`linux-x11`, `linux-wayland`, `macos`, `windows`), the screen size you must
target, whether the agent is `read_only`, and any `missing_tools` that will make
later calls fail. **Never guess coordinates against an assumed screen size** —
take the size from `health` and the layout from a screenshot.

```bash
remotectl --host laptop health
```

If it cannot reach the agent, see `reference/setup.md`: the usual causes are a
dropped SSH tunnel, a daemon that was never started, or a stale token.

## The loop that works

GUI automation is open-loop guessing unless you look between steps. Work in
observe → act → observe:

1. **Screenshot.** `remotectl screenshot -o /tmp/step1.png --scale 1400`
2. **Read it** with the Read tool. Locate the target by eye and note its pixel
   coordinates — remember the screenshot may be downscaled, so multiply back up
   by `full_width / scaled_width` before clicking.
3. **Act.** One meaningful step, not five.
4. **Screenshot again** and confirm the step landed before continuing.

Skipping step 4 is how automations click "Delete" on the wrong dialog.

## Commands

```bash
remotectl --host laptop screenshot -o /tmp/s.png       # whole screen
remotectl screenshot --region 0,0,800,600 -o /tmp/s.png
remotectl screenshot --scale 1400 -o /tmp/s.png        # downscale, cheaper to read
remotectl move 640 400
remotectl click 640 400                                # move, then click
remotectl click --button right --count 1 200 300
remotectl click --count 2 640 400                      # double click
remotectl drag 100 100 400 300
remotectl scroll 0 -3                                  # dy<0 scrolls down
remotectl type "hello world"
remotectl key ctrl+s
remotectl key alt+tab enter                            # several combos in order
remotectl clipboard get
remotectl clipboard set "text to paste"
remotectl tunnel me@laptop.local                       # prints the ssh command
```

Every command takes `--host NAME` (from `~/.config/computer-remote/hosts.json`)
or an explicit `--url` and `--token`.

### Key syntax

`ctrl`, `alt`, `shift`, and `cmd`/`super`/`win` are the modifiers, joined with
`+`: `ctrl+shift+t`, `cmd+space`, `alt+f4`. Named keys are `enter`, `escape`,
`tab`, `space`, `backspace`, `delete`, `insert`, `up`, `down`, `left`, `right`,
`home`, `end`, `pageup`, `pagedown`, `f1`–`f12`. Anything else must be a single
character. The agent translates these per platform, so write the combo once and
it works on all three.

Type literal text with `type`, not `key` — `key` is for shortcuts.

### Batching

Several actions in one round trip, applied in order, when you already know the
sequence is safe (`sleep` waits between steps, in milliseconds):

```bash
echo '[
  {"type": "click", "x": 640, "y": 400},
  {"type": "sleep", "ms": 300},
  {"type": "text", "text": "search term"},
  {"type": "key", "keys": "enter"}
]' | remotectl --host laptop do -
```

Keep batches short and screenshot after each one. A batch stops at the first
failing action and reports how many ran.

## Rules that keep this safe

- **Confirm before destructive clicks.** Closing unsaved work, sending a
  message, confirming a purchase, emptying a trash, running an installer — ask
  the user first. It is their real machine and there is no undo.
- **Screenshots capture everything on screen**, including mail, chats,
  passwords, and anything a password manager has open. Prefer `--region` around
  the window you need, mention what you saw only as far as the task requires,
  and never write full-screen captures somewhere they will be committed or
  published.
- **Never type secrets you were not given for that purpose.** If a login is
  needed, stop and hand control back to the user.
- **Suggest `--read-only`** when the user only wants to look at the machine: the
  agent then serves screenshots and refuses all input.
- **Do not widen the network exposure.** The agent belongs on `127.0.0.1` behind
  an SSH tunnel. If asked to bind it to `0.0.0.0`, say why that is a bad idea
  (anyone who reaches the port and guesses the token owns the desktop) before
  doing it.

## When something does not work

`reference/troubleshooting.md` covers the common failures: `missing tool`
errors, macOS Accessibility and Screen Recording permissions, Wayland vs X11,
blank or black screenshots, and clicks that land but do nothing.

`reference/protocol.md` documents the HTTP API if you need to drive the agent
from your own script instead of `remotectl`.

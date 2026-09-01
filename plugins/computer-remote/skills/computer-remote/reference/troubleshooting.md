# Troubleshooting

## `cannot reach agent at http://127.0.0.1:8765`

The tunnel or the daemon is down. In order:

1. Is the SSH tunnel alive? `ss -tlnp | grep 8765` on the controlling machine.
2. Is the agent running on the target? `pgrep -af remote_agentd.py`.
3. Does the port match on both ends? `--port` on the agent, the `-L` mapping,
   and `url` in `hosts.json` all have to agree.

## `401 missing or invalid bearer token`

The client and agent disagree about the token. The agent reads `--token`, then
`COMPUTER_REMOTE_TOKEN`, then `~/.config/computer-remote/token`; the client
reads `--token`, then the host entry in `hosts.json`, then the env var, then the
same token file **on the controlling machine**. A trailing newline is stripped
on both sides, but a copy-paste that lost a character is not.

## `403 this agent runs in --read-only mode`

Intentional. Restart the agent without `--read-only` — and check with the user
first, since they presumably chose it.

## `501 missing tool: xdotool` (or `grim`, `cliclick`, …)

The backend's helper is not installed. `python3 remote_agentd.py --check` lists
everything missing; `reference/setup.md` has the install commands per platform.

## Screenshots are black, blank, or just the wallpaper

- **macOS**: Screen Recording permission is missing for the process running the
  agent. Grant it, then restart the agent.
- **Linux**: the agent is not attached to the graphical session — no `DISPLAY`
  (X11) or `WAYLAND_DISPLAY` (Wayland). Start it from inside the desktop
  session, not from a bare system service.
- **Any**: the screen is locked or asleep. Nothing can capture through a lock
  screen; ask the user to unlock.
- **Compositor windows** (some GPU-accelerated video, DRM content) come out
  black by design.

## Clicks and keystrokes do nothing

- **macOS**: Accessibility permission is missing — input is dropped silently,
  with no error. This is the single most common macOS symptom.
- **Wayland**: `ydotool`'s daemon is not running, or the user lacks access to
  `/dev/uinput`.
- **Focus**: input goes to whatever window has focus, not to the coordinates you
  clicked earlier. Click the window first, screenshot to confirm focus, then
  type.
- **Timing**: the app had not finished opening. Insert a `sleep` action and
  re-screenshot.

## Clicks land in the wrong place

Almost always a scaling mistake. `--scale 1400` gives you a *downscaled* image;
coordinates read off it must be multiplied by `full_width / scaled_width` before
being sent. HiDPI displays add a second factor: macOS reports points while the
capture is in pixels, so a Retina screenshot can be exactly 2× the coordinate
space. Take one full-size screenshot, click a known landmark, and screenshot
again to calibrate before a long sequence.

## Multi-monitor

The agent captures and addresses the primary screen. Secondary monitors sit at
coordinates outside its bounds — reachable with explicit `move`/`click`
coordinates on X11 and Windows, but not visible in the screenshot. Ask the user
to move the window to the primary display.

## Keys with `cmd` on Windows

`meta`/`win` is not expressible through SendKeys; the agent returns `501`. Use
an app-level shortcut instead.

## Everything is slow

Each action shells out to a helper process; on Windows every call spawns
PowerShell, which costs a few hundred milliseconds. Batch related actions into a
single `remotectl do` request instead of one call per keystroke, and use
`--scale` to keep screenshots small.

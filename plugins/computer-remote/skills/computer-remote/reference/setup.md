# Setting up a target machine

Two pieces: the **agent** (`scripts/remote_agentd.py`) on the machine being
controlled, and **`remotectl`** on the machine Claude Code runs on. Only Python
3.9+ is required on both sides; the agent shells out to platform tools for the
actual input.

## 1. Install the platform tools on the target

| Platform | Screenshots | Input | Clipboard |
|---|---|---|---|
| Linux / X11 | `imagemagick` (or `scrot`) | `xdotool` | `xclip` or `xsel` |
| Linux / Wayland | `grim` | `ydotool` (+ its daemon) | `wl-clipboard` |
| macOS | built in (`screencapture`) | `cliclick` (`brew install cliclick`) | built in |
| Windows | built in (PowerShell + .NET) | built in (SendKeys / user32) | built in |

Debian/Ubuntu X11:

```bash
sudo apt install xdotool imagemagick xclip
```

Check what the agent thinks it has, without starting a server:

```bash
python3 remote_agentd.py --check
```

It prints the detected backend, the screen size, and anything missing.

### macOS permissions

macOS gates both halves of this behind TCC. In **System Settings → Privacy &
Security**, grant the terminal (or whatever launches the agent) both:

- **Screen Recording** — otherwise screenshots come back empty or wallpaper-only.
- **Accessibility** — otherwise clicks and keystrokes are silently dropped.

Restart the terminal after granting; the permission is read at process start.

### Wayland

Wayland has no global input protocol, so input goes through `ydotool`, which
needs its daemon running and access to `/dev/uinput`:

```bash
sudo systemctl enable --now ydotool
```

If that is not workable, run the agent with `--read-only` for screenshots only,
or use an X11 session.

## 2. Create a token on the target

```bash
mkdir -p ~/.config/computer-remote
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > ~/.config/computer-remote/token
chmod 600 ~/.config/computer-remote/token
```

## 3. Start the agent

```bash
python3 remote_agentd.py                 # 127.0.0.1:8765, full control
python3 remote_agentd.py --read-only     # screenshots only, input refused
python3 remote_agentd.py --port 8766
```

It binds loopback by default and refuses every request without the bearer token.
Leave it that way: with a non-loopback `--bind`, anyone who can reach the port
and guess the token controls the desktop.

The agent must run **inside the graphical session** — as the logged-in desktop
user, with `DISPLAY`/`WAYLAND_DISPLAY` set. A daemon launched from a headless
system service has no screen to capture.

To keep it running across logins, add it to the desktop session's autostart
(GNOME "Startup Applications", a user-level `systemd --user` unit, or macOS
Login Items). A `systemd --user` unit:

```ini
[Unit]
Description=computer-remote agent
[Service]
ExecStart=/usr/bin/python3 %h/computer-remote/remote_agentd.py
Restart=on-failure
[Install]
WantedBy=default.target
```

## 4. Tunnel from the controlling machine

```bash
ssh -N -L 8765:127.0.0.1:8765 me@laptop.local
```

`remotectl tunnel me@laptop.local` prints exactly this line for the configured
port. Keep it in its own terminal, or add `-f` to background it. `autossh`
survives flaky links.

## 5. Name the host

Copy `config/hosts.example.json` to `~/.config/computer-remote/hosts.json`:

```json
{
  "laptop": {
    "url": "http://127.0.0.1:8765",
    "token": "the token from step 2",
    "ssh": "me@laptop.local"
  }
}
```

```bash
chmod 600 ~/.config/computer-remote/hosts.json
remotectl --host laptop health
```

Credentials also come from `COMPUTER_REMOTE_TOKEN` / `COMPUTER_REMOTE_URL`, or
`--token` / `--url` per invocation. `hosts.json` holds tokens in cleartext —
keep it mode 600 and out of version control.

## Putting `remotectl` on PATH

```bash
ln -s "$PWD/scripts/remotectl" ~/.local/bin/remotectl
```

Otherwise call it as `python3 /path/to/scripts/remotectl`.

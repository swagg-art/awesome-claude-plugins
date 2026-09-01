#!/usr/bin/env python3
"""computer-remote agent daemon.

Runs on the machine you want to control. Exposes a small JSON/HTTP API for
screenshots, mouse input, keyboard input and the clipboard.

Security model: bind to loopback only (the default) and reach it from another
machine through an SSH tunnel. Every request must carry a bearer token.

  ssh -N -L 8765:127.0.0.1:8765 user@target

Start it on the target machine with:

  python3 remote_agentd.py --token-file ~/.config/computer-remote/token
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"
DEFAULT_PORT = 8765
MAX_BODY = 1 << 22  # 4 MiB
DEFAULT_TOKEN_FILE = os.path.expanduser("~/.config/computer-remote/token")


class AgentError(Exception):
    """Any failure that should be reported to the caller as a 4xx/5xx."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


def run(cmd: list[str], *, input_bytes: bytes | None = None, capture: bool = True) -> bytes:
    try:
        proc = subprocess.run(
            cmd,
            input=input_bytes,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise AgentError(f"missing tool: {cmd[0]}", 501) from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentError(f"timed out: {shlex.join(cmd)}", 504) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise AgentError(f"{shlex.join(cmd)} failed ({proc.returncode}): {detail}")
    return proc.stdout or b""


def which(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


# --------------------------------------------------------------------------
# key normalisation
# --------------------------------------------------------------------------

MOD_CANON = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
    "cmd": "meta",
    "command": "meta",
    "meta": "meta",
    "super": "meta",
    "win": "meta",
}

KEY_ALIASES = {
    "return": "enter",
    "esc": "escape",
    "del": "delete",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "pgdown": "pagedown",
    "ins": "insert",
}


def parse_combo(combo: str) -> tuple[list[str], str]:
    """'ctrl+shift+t' -> (['ctrl', 'shift'], 't')."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise AgentError(f"empty key combo: {combo!r}", 400)
    # a trailing literal '+' (e.g. 'ctrl++') collapses to the plus key
    if combo.strip().endswith("+") and parts[-1] in MOD_CANON:
        parts.append("plus")
    mods: list[str] = []
    for part in parts[:-1]:
        if part not in MOD_CANON:
            raise AgentError(f"unknown modifier: {part!r}", 400)
        canon = MOD_CANON[part]
        if canon not in mods:
            mods.append(canon)
    key = parts[-1]
    key = KEY_ALIASES.get(key, key)
    return mods, key


# --------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------


class Backend:
    name = "base"
    requires: tuple[str, ...] = ()

    def missing_tools(self) -> list[str]:
        return [tool for tool in self.requires if not shutil.which(tool)]

    # -- capabilities ------------------------------------------------------
    def screen_size(self) -> tuple[int, int]:
        raise AgentError("screen size unsupported on this backend", 501)

    def screenshot(self, path: str, region: tuple[int, int, int, int] | None) -> None:
        raise AgentError("screenshot unsupported on this backend", 501)

    def move(self, x: int, y: int) -> None:
        raise AgentError("mouse unsupported on this backend", 501)

    def cursor_position(self) -> tuple[int, int]:
        raise AgentError("cursor position unsupported on this backend", 501)

    def click(self, button: str, count: int) -> None:
        raise AgentError("mouse unsupported on this backend", 501)

    def mouse_down(self, button: str) -> None:
        raise AgentError("mouse unsupported on this backend", 501)

    def mouse_up(self, button: str) -> None:
        raise AgentError("mouse unsupported on this backend", 501)

    def scroll(self, dx: int, dy: int) -> None:
        raise AgentError("scroll unsupported on this backend", 501)

    def type_text(self, text: str) -> None:
        raise AgentError("typing unsupported on this backend", 501)

    def key(self, combo: str) -> None:
        raise AgentError("keys unsupported on this backend", 501)

    def clipboard_get(self) -> str:
        raise AgentError("clipboard unsupported on this backend", 501)

    def clipboard_set(self, text: str) -> None:
        raise AgentError("clipboard unsupported on this backend", 501)

    # -- helpers -----------------------------------------------------------
    def resize(self, path: str, max_width: int) -> None:
        tool = which("magick", "convert")
        if not tool:
            return
        cmd = [tool]
        if os.path.basename(tool) == "magick":
            cmd.append("convert")
        run(cmd + [path, "-resize", f"{max_width}x>", path])


X11_BUTTONS = {"left": "1", "middle": "2", "right": "3"}

X11_KEYS = {
    "enter": "Return",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "insert": "Insert",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "plus": "plus",
    "minus": "minus",
}

X11_MODS = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "meta": "super"}


class X11Backend(Backend):
    name = "linux-x11"
    requires = ("xdotool",)

    def _keysym(self, key: str) -> str:
        if key in X11_KEYS:
            return X11_KEYS[key]
        if re.fullmatch(r"f\d{1,2}", key):
            return key.upper()
        if len(key) == 1:
            return key
        raise AgentError(f"unknown key: {key!r}", 400)

    def screen_size(self) -> tuple[int, int]:
        out = run(["xdotool", "getdisplaygeometry"]).decode().split()
        return int(out[0]), int(out[1])

    def screenshot(self, path: str, region: tuple[int, int, int, int] | None) -> None:
        magick = which("magick", "import")
        if magick:
            cmd = [magick]
            if os.path.basename(magick) == "magick":
                cmd.append("import")
            cmd += ["-window", "root"]
            if region:
                x, y, w, h = region
                cmd += ["-crop", f"{w}x{h}+{x}+{y}", "+repage"]
            run(cmd + [path])
            return
        if shutil.which("scrot"):
            cmd = ["scrot", "--overwrite"]
            if region:
                x, y, w, h = region
                cmd += ["-a", f"{x},{y},{w},{h}"]
            run(cmd + [path])
            return
        if shutil.which("gnome-screenshot"):
            run(["gnome-screenshot", "-f", path])
            return
        raise AgentError("no screenshot tool found (install imagemagick or scrot)", 501)

    def move(self, x: int, y: int) -> None:
        run(["xdotool", "mousemove", "--sync", str(x), str(y)])

    def cursor_position(self) -> tuple[int, int]:
        out = run(["xdotool", "getmouselocation", "--shell"]).decode()
        values = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
        return int(values["X"]), int(values["Y"])

    def click(self, button: str, count: int) -> None:
        run(["xdotool", "click", "--repeat", str(count), "--delay", "80", X11_BUTTONS[button]])

    def mouse_down(self, button: str) -> None:
        run(["xdotool", "mousedown", X11_BUTTONS[button]])

    def mouse_up(self, button: str) -> None:
        run(["xdotool", "mouseup", X11_BUTTONS[button]])

    def scroll(self, dx: int, dy: int) -> None:
        for button, amount in (("4", max(dy, 0)), ("5", max(-dy, 0)), ("6", max(-dx, 0)), ("7", max(dx, 0))):
            for _ in range(amount):
                run(["xdotool", "click", button])

    def type_text(self, text: str) -> None:
        run(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text])

    def key(self, combo: str) -> None:
        mods, key = parse_combo(combo)
        sequence = "+".join([X11_MODS[m] for m in mods] + [self._keysym(key)])
        run(["xdotool", "key", "--clearmodifiers", sequence])

    def clipboard_get(self) -> str:
        tool = which("xclip", "xsel")
        if not tool:
            raise AgentError("install xclip or xsel for clipboard access", 501)
        if os.path.basename(tool) == "xclip":
            return run([tool, "-selection", "clipboard", "-o"]).decode("utf-8", "replace")
        return run([tool, "--clipboard", "--output"]).decode("utf-8", "replace")

    def clipboard_set(self, text: str) -> None:
        tool = which("xclip", "xsel")
        if not tool:
            raise AgentError("install xclip or xsel for clipboard access", 501)
        args = [tool, "-selection", "clipboard"] if os.path.basename(tool) == "xclip" else [tool, "--clipboard", "--input"]
        run(args, input_bytes=text.encode(), capture=False)


YDOTOOL_KEYS = {
    "enter": "KEY_ENTER",
    "escape": "KEY_ESC",
    "tab": "KEY_TAB",
    "space": "KEY_SPACE",
    "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE",
    "insert": "KEY_INSERT",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "home": "KEY_HOME",
    "end": "KEY_END",
    "pageup": "KEY_PAGEUP",
    "pagedown": "KEY_PAGEDOWN",
    "plus": "KEY_EQUAL",
    "minus": "KEY_MINUS",
}

YDOTOOL_MODS = {"ctrl": "KEY_LEFTCTRL", "alt": "KEY_LEFTALT", "shift": "KEY_LEFTSHIFT", "meta": "KEY_LEFTMETA"}

YDOTOOL_BUTTONS = {"left": "0", "middle": "2", "right": "1"}


class WaylandBackend(Backend):
    name = "linux-wayland"
    requires = ("ydotool", "grim")

    def _code(self, key: str) -> str:
        if key in YDOTOOL_KEYS:
            return YDOTOOL_KEYS[key]
        if re.fullmatch(r"f\d{1,2}", key):
            return f"KEY_{key.upper()}"
        if len(key) == 1 and key.isalpha():
            return f"KEY_{key.upper()}"
        if len(key) == 1 and key.isdigit():
            return f"KEY_{key}"
        raise AgentError(f"unknown key: {key!r}", 400)

    def screen_size(self) -> tuple[int, int]:
        if not shutil.which("wlr-randr"):
            raise AgentError("install wlr-randr to report screen size on wayland", 501)
        out = run(["wlr-randr"]).decode()
        match = re.search(r"(\d{3,5})x(\d{3,5})\s+px.*current", out)
        if not match:
            raise AgentError("could not parse wlr-randr output")
        return int(match.group(1)), int(match.group(2))

    def screenshot(self, path: str, region: tuple[int, int, int, int] | None) -> None:
        cmd = ["grim"]
        if region:
            x, y, w, h = region
            cmd += ["-g", f"{x},{y} {w}x{h}"]
        run(cmd + [path])

    def move(self, x: int, y: int) -> None:
        run(["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)])

    def click(self, button: str, count: int) -> None:
        code = YDOTOOL_BUTTONS[button]
        for _ in range(count):
            run(["ydotool", "click", f"0xC{code}"])

    def mouse_down(self, button: str) -> None:
        run(["ydotool", "click", f"0x4{YDOTOOL_BUTTONS[button]}"])

    def mouse_up(self, button: str) -> None:
        run(["ydotool", "click", f"0x8{YDOTOOL_BUTTONS[button]}"])

    def scroll(self, dx: int, dy: int) -> None:
        run(["ydotool", "mousemove", "--wheel", "-x", str(dx), "-y", str(-dy)])

    def type_text(self, text: str) -> None:
        run(["ydotool", "type", "--key-delay", "12", "--", text])

    def key(self, combo: str) -> None:
        mods, key = parse_combo(combo)
        codes = [YDOTOOL_MODS[m] for m in mods] + [self._code(key)]
        pressed = [f"{code}:1" for code in codes]
        released = [f"{code}:0" for code in reversed(codes)]
        run(["ydotool", "key", *pressed, *released])

    def clipboard_get(self) -> str:
        return run(["wl-paste", "--no-newline"]).decode("utf-8", "replace")

    def clipboard_set(self, text: str) -> None:
        run(["wl-copy"], input_bytes=text.encode(), capture=False)


MAC_KEY_CODES = {
    "enter": 36,
    "tab": 48,
    "space": 49,
    "backspace": 51,
    "escape": 53,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "delete": 117,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
}

MAC_MODS = {"ctrl": "control down", "alt": "option down", "shift": "shift down", "meta": "command down"}

MAC_LITERALS = {"plus": "+", "minus": "-"}


class MacBackend(Backend):
    name = "macos"
    requires = ("screencapture", "osascript")

    def _osascript(self, script: str) -> str:
        return run(["osascript", "-e", script]).decode("utf-8", "replace").strip()

    def screen_size(self) -> tuple[int, int]:
        out = self._osascript(
            'tell application "Finder" to get bounds of window of desktop'
        )
        parts = [int(p.strip()) for p in out.split(",")]
        return parts[2], parts[3]

    def screenshot(self, path: str, region: tuple[int, int, int, int] | None) -> None:
        cmd = ["screencapture", "-x", "-t", "png"]
        if region:
            x, y, w, h = region
            cmd += ["-R", f"{x},{y},{w},{h}"]
        run(cmd + [path], capture=False)

    def resize(self, path: str, max_width: int) -> None:
        if shutil.which("sips"):
            run(["sips", "--resampleWidth", str(max_width), path], capture=False)
            return
        super().resize(path, max_width)

    def _cliclick(self) -> str:
        tool = shutil.which("cliclick")
        if not tool:
            raise AgentError(
                "install cliclick for mouse control on macOS: brew install cliclick", 501
            )
        return tool

    def move(self, x: int, y: int) -> None:
        run([self._cliclick(), f"m:{x},{y}"], capture=False)

    def cursor_position(self) -> tuple[int, int]:
        out = run([self._cliclick(), "p"]).decode().strip()
        x, y = out.split(",")
        return int(x), int(y)

    def click(self, button: str, count: int) -> None:
        verb = {"left": "c", "right": "rc", "middle": "c"}[button]
        if button == "middle":
            raise AgentError("middle click is not supported on macOS", 501)
        for _ in range(count):
            run([self._cliclick(), f"{verb}:."], capture=False)

    def mouse_down(self, button: str) -> None:
        if button != "left":
            raise AgentError("only left-button drag is supported on macOS", 501)
        run([self._cliclick(), "dd:."], capture=False)

    def mouse_up(self, button: str) -> None:
        if button != "left":
            raise AgentError("only left-button drag is supported on macOS", 501)
        run([self._cliclick(), "du:."], capture=False)

    def scroll(self, dx: int, dy: int) -> None:
        if dx:
            raise AgentError("horizontal scroll is not supported on macOS", 501)
        run([self._cliclick(), f"w:{dy}"], capture=False)

    def type_text(self, text: str) -> None:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        self._osascript(f'tell application "System Events" to keystroke "{escaped}"')

    def key(self, combo: str) -> None:
        mods, key = parse_combo(combo)
        using = ""
        if mods:
            using = " using {" + ", ".join(MAC_MODS[m] for m in mods) + "}"
        if key in MAC_KEY_CODES:
            action = f"key code {MAC_KEY_CODES[key]}"
        else:
            literal = MAC_LITERALS.get(key, key)
            if len(literal) != 1:
                raise AgentError(f"unknown key: {key!r}", 400)
            escaped = literal.replace("\\", "\\\\").replace('"', '\\"')
            action = f'keystroke "{escaped}"'
        self._osascript(f'tell application "System Events" to {action}{using}')

    def clipboard_get(self) -> str:
        return run(["pbpaste"]).decode("utf-8", "replace")

    def clipboard_set(self, text: str) -> None:
        run(["pbcopy"], input_bytes=text.encode(), capture=False)


WIN_KEYS = {
    "enter": "{ENTER}",
    "escape": "{ESC}",
    "tab": "{TAB}",
    "space": " ",
    "backspace": "{BACKSPACE}",
    "delete": "{DEL}",
    "insert": "{INSERT}",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
    "home": "{HOME}",
    "end": "{END}",
    "pageup": "{PGUP}",
    "pagedown": "{PGDN}",
    "plus": "{+}",
    "minus": "-",
}

WIN_MODS = {"ctrl": "^", "alt": "%", "shift": "+"}

WIN_MOUSE_EVENTS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}

WIN_PRELUDE = """
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class CRNative {
  [DllImport("user32.dll")] public static extern void mouse_event(int f, int dx, int dy, int d, int extra);
}
'@
"""


class WindowsBackend(Backend):
    name = "windows"
    requires = ("powershell",)

    def _ps(self, script: str) -> str:
        return run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", WIN_PRELUDE + script]
        ).decode("utf-8", "replace").strip()

    def _escape(self, text: str) -> str:
        return text.replace("'", "''")

    def screen_size(self) -> tuple[int, int]:
        out = self._ps(
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "Write-Output \"$($b.Width) $($b.Height)\""
        )
        width, height = out.split()
        return int(width), int(height)

    def screenshot(self, path: str, region: tuple[int, int, int, int] | None) -> None:
        if region:
            x, y, w, h = region
        else:
            x = y = 0
            w, h = self.screen_size()
        self._ps(
            f"$bmp=New-Object System.Drawing.Bitmap {w},{h}; "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            f"$g.CopyFromScreen({x},{y},0,0,$bmp.Size); "
            f"$bmp.Save('{self._escape(path)}',[System.Drawing.Imaging.ImageFormat]::Png); "
            "$g.Dispose(); $bmp.Dispose()"
        )

    def move(self, x: int, y: int) -> None:
        self._ps(
            "[System.Windows.Forms.Cursor]::Position="
            f"New-Object System.Drawing.Point({x},{y})"
        )

    def cursor_position(self) -> tuple[int, int]:
        out = self._ps(
            "$p=[System.Windows.Forms.Cursor]::Position; Write-Output \"$($p.X) $($p.Y)\""
        )
        x, y = out.split()
        return int(x), int(y)

    def click(self, button: str, count: int) -> None:
        down, up = WIN_MOUSE_EVENTS[button]
        body = f"[CRNative]::mouse_event({down},0,0,0,0); [CRNative]::mouse_event({up},0,0,0,0);"
        self._ps(f"1..{count} | ForEach-Object {{ {body} Start-Sleep -Milliseconds 80 }}")

    def mouse_down(self, button: str) -> None:
        self._ps(f"[CRNative]::mouse_event({WIN_MOUSE_EVENTS[button][0]},0,0,0,0)")

    def mouse_up(self, button: str) -> None:
        self._ps(f"[CRNative]::mouse_event({WIN_MOUSE_EVENTS[button][1]},0,0,0,0)")

    def scroll(self, dx: int, dy: int) -> None:
        script = ""
        if dy:
            script += f"[CRNative]::mouse_event(0x0800,0,0,{dy * 120},0);"
        if dx:
            script += f"[CRNative]::mouse_event(0x01000,0,0,{dx * 120},0);"
        if script:
            self._ps(script)

    def type_text(self, text: str) -> None:
        escaped = re.sub(r"([+^%~(){}\[\]])", r"{\1}", text)
        self._ps(f"[System.Windows.Forms.SendKeys]::SendWait('{self._escape(escaped)}')")

    def key(self, combo: str) -> None:
        mods, key = parse_combo(combo)
        if "meta" in mods:
            raise AgentError("the Windows key is not supported by SendKeys", 501)
        if key in WIN_KEYS:
            token = WIN_KEYS[key]
        elif re.fullmatch(r"f\d{1,2}", key):
            token = "{" + key.upper() + "}"
        elif len(key) == 1:
            token = re.sub(r"([+^%~(){}\[\]])", r"{\1}", key)
        else:
            raise AgentError(f"unknown key: {key!r}", 400)
        sequence = "".join(WIN_MODS[m] for m in mods) + token
        self._ps(f"[System.Windows.Forms.SendKeys]::SendWait('{self._escape(sequence)}')")

    def clipboard_get(self) -> str:
        return self._ps("Get-Clipboard -Raw")

    def clipboard_set(self, text: str) -> None:
        self._ps(f"Set-Clipboard -Value '{self._escape(text)}'")


def detect_backend(forced: str | None = None) -> Backend:
    backends = {
        "linux-x11": X11Backend,
        "linux-wayland": WaylandBackend,
        "macos": MacBackend,
        "windows": WindowsBackend,
    }
    if forced:
        if forced not in backends:
            raise SystemExit(f"unknown backend {forced!r}; pick one of {', '.join(backends)}")
        return backends[forced]()
    system = platform.system()
    if system == "Darwin":
        return MacBackend()
    if system == "Windows":
        return WindowsBackend()
    if system == "Linux":
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            return WaylandBackend()
        return X11Backend()
    raise SystemExit(f"unsupported platform: {system}")


# --------------------------------------------------------------------------
# action dispatch
# --------------------------------------------------------------------------

BUTTONS = ("left", "right", "middle")


def _int(action: dict, key: str, default: int | None = None) -> int:
    if key not in action:
        if default is None:
            raise AgentError(f"action {action.get('type')!r} requires {key!r}", 400)
        return default
    try:
        return int(action[key])
    except (TypeError, ValueError) as exc:
        raise AgentError(f"{key!r} must be an integer", 400) from exc


def _button(action: dict) -> str:
    button = str(action.get("button", "left")).lower()
    if button not in BUTTONS:
        raise AgentError(f"button must be one of {', '.join(BUTTONS)}", 400)
    return button


def perform(backend: Backend, action: dict, max_sleep_ms: int = 5000) -> None:
    kind = str(action.get("type", "")).lower()
    if kind == "move":
        backend.move(_int(action, "x"), _int(action, "y"))
    elif kind == "click":
        if "x" in action or "y" in action:
            backend.move(_int(action, "x"), _int(action, "y"))
        count = _int(action, "count", 1)
        if not 1 <= count <= 5:
            raise AgentError("count must be between 1 and 5", 400)
        backend.click(_button(action), count)
    elif kind == "mousedown":
        backend.mouse_down(_button(action))
    elif kind == "mouseup":
        backend.mouse_up(_button(action))
    elif kind == "drag":
        backend.move(_int(action, "x"), _int(action, "y"))
        backend.mouse_down(_button(action))
        time.sleep(0.1)
        backend.move(_int(action, "to_x"), _int(action, "to_y"))
        time.sleep(0.1)
        backend.mouse_up(_button(action))
    elif kind == "scroll":
        backend.scroll(_int(action, "dx", 0), _int(action, "dy", 0))
    elif kind == "text":
        text = action.get("text")
        if not isinstance(text, str):
            raise AgentError("text action requires a string 'text'", 400)
        backend.type_text(text)
    elif kind == "key":
        keys = action.get("keys")
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, list) or not keys:
            raise AgentError("key action requires 'keys'", 400)
        for combo in keys:
            backend.key(str(combo))
    elif kind == "sleep":
        millis = _int(action, "ms", 200)
        if not 0 <= millis <= max_sleep_ms:
            raise AgentError(f"sleep ms must be between 0 and {max_sleep_ms}", 400)
        time.sleep(millis / 1000)
    else:
        raise AgentError(f"unknown action type: {kind!r}", 400)


def parse_region(value) -> tuple[int, int, int, int] | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = [part for part in re.split(r"[,\s]+", value.strip()) if part]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise AgentError("region must be [x, y, width, height]", 400)
    try:
        x, y, w, h = (int(part) for part in value)
    except (TypeError, ValueError) as exc:
        raise AgentError("region values must be integers", 400) from exc
    if w <= 0 or h <= 0:
        raise AgentError("region width and height must be positive", 400)
    return x, y, w, h


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = f"computer-remote/{VERSION}"
    backend: Backend
    token: str
    allow_input: bool

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - stdlib hook
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}\n")

    # -- plumbing ----------------------------------------------------------
    def _send(self, status: int, payload: dict, raw: bytes | None = None, ctype: str = "application/json") -> None:
        body = raw if raw is not None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        return hmac.compare_digest(header[len(prefix):].strip(), self.token)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise AgentError("request body too large", 413)
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise AgentError(f"invalid JSON: {exc}", 400) from exc
        if not isinstance(data, dict):
            raise AgentError("request body must be a JSON object", 400)
        return data

    def _guard_input(self) -> None:
        if not self.allow_input:
            raise AgentError("this agent runs in --read-only mode; input is disabled", 403)

    # -- routes ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        try:
            if not self._authorized():
                self._send(401, {"error": "missing or invalid bearer token"})
                return
            if path == "/health":
                self._send(200, self._health())
            elif path == "/screenshot" and method == "POST":
                self._screenshot()
            elif path == "/input" and method == "POST":
                self._input()
            elif path == "/clipboard":
                self._clipboard(method)
            else:
                self._send(404, {"error": f"no route for {method} {path}"})
        except AgentError as exc:
            self._send(exc.status, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _health(self) -> dict:
        info = {
            "ok": True,
            "version": VERSION,
            "platform": platform.platform(),
            "backend": self.backend.name,
            "read_only": not self.allow_input,
            "missing_tools": self.backend.missing_tools(),
        }
        try:
            width, height = self.backend.screen_size()
            info["screen"] = {"width": width, "height": height}
        except AgentError as exc:
            info["screen_error"] = str(exc)
        try:
            x, y = self.backend.cursor_position()
            info["cursor"] = {"x": x, "y": y}
        except AgentError:
            pass
        return info

    def _screenshot(self) -> None:
        body = self._body()
        region = parse_region(body.get("region"))
        scale = body.get("scale")
        fd, path = tempfile.mkstemp(prefix="computer-remote-", suffix=".png")
        os.close(fd)
        try:
            self.backend.screenshot(path, region)
            if scale:
                try:
                    max_width = int(scale)
                except (TypeError, ValueError) as exc:
                    raise AgentError("scale must be an integer pixel width", 400) from exc
                if max_width > 0:
                    self.backend.resize(path, max_width)
            with open(path, "rb") as handle:
                data = handle.read()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._send(200, {}, raw=data, ctype="image/png")

    def _input(self) -> None:
        self._guard_input()
        body = self._body()
        actions = body.get("actions")
        if isinstance(actions, dict):
            actions = [actions]
        if not isinstance(actions, list) or not actions:
            raise AgentError("expected a non-empty 'actions' array", 400)
        if len(actions) > 64:
            raise AgentError("at most 64 actions per request", 400)
        done = 0
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                raise AgentError(f"action {index} must be an object", 400)
            perform(self.backend, action)
            done += 1
        self._send(200, {"ok": True, "performed": done})

    def _clipboard(self, method: str) -> None:
        if method == "GET":
            self._send(200, {"text": self.backend.clipboard_get()})
            return
        self._guard_input()
        body = self._body()
        text = body.get("text")
        if not isinstance(text, str):
            raise AgentError("clipboard set requires a string 'text'", 400)
        self.backend.clipboard_set(text)
        self._send(200, {"ok": True})


def load_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token
    env = os.environ.get("COMPUTER_REMOTE_TOKEN")
    if env:
        return env
    path = os.path.expanduser(args.token_file or DEFAULT_TOKEN_FILE)
    if os.path.exists(path):
        token = open(path, encoding="utf-8").read().strip()
        if token:
            return token
    raise SystemExit(
        "no token found. Create one with:\n"
        f"  mkdir -p {os.path.dirname(DEFAULT_TOKEN_FILE)} && "
        f"python3 -c 'import secrets;print(secrets.token_urlsafe(32))' > {DEFAULT_TOKEN_FILE} && "
        f"chmod 600 {DEFAULT_TOKEN_FILE}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="computer-remote agent daemon")
    parser.add_argument("--bind", default="127.0.0.1", help="address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--token", help="bearer token (prefer --token-file or COMPUTER_REMOTE_TOKEN)")
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--backend", help="force a backend: linux-x11, linux-wayland, macos, windows")
    parser.add_argument("--read-only", action="store_true", help="serve screenshots only, refuse input")
    parser.add_argument("--check", action="store_true", help="print backend diagnostics and exit")
    args = parser.parse_args(argv)

    backend = detect_backend(args.backend)

    if args.check:
        report = {"backend": backend.name, "missing_tools": backend.missing_tools()}
        try:
            width, height = backend.screen_size()
            report["screen"] = {"width": width, "height": height}
        except AgentError as exc:
            report["screen_error"] = str(exc)
        print(json.dumps(report, indent=2))
        return 0 if not report["missing_tools"] else 1

    token = load_token(args)
    if len(token) < 16:
        raise SystemExit("token must be at least 16 characters")

    missing = backend.missing_tools()
    if missing:
        print(f"warning: missing tools for {backend.name}: {', '.join(missing)}", file=sys.stderr)

    Handler.backend = backend
    Handler.token = token
    Handler.allow_input = not args.read_only

    if args.bind not in ("127.0.0.1", "::1", "localhost"):
        print(
            f"warning: binding to {args.bind} exposes desktop control to the network. "
            "Prefer 127.0.0.1 plus an SSH tunnel.",
            file=sys.stderr,
        )

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    mode = "read-only" if args.read_only else "full control"
    print(f"computer-remote {VERSION} [{backend.name}, {mode}] on http://{args.bind}:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Agent HTTP API

Base URL is wherever the agent is reachable — with the standard SSH tunnel,
`http://127.0.0.1:8765`. Every request needs `Authorization: Bearer <token>`;
without it the agent answers `401` and does nothing. Bodies are JSON; the
screenshot response is raw PNG. Errors come back as `{"error": "..."}` with a
meaningful status (`400` bad request, `401` bad token, `403` read-only mode,
`404` unknown route, `501` unsupported on this backend, `504` tool timeout).

## `GET /health`

```json
{
  "ok": true,
  "version": "1.0.0",
  "platform": "Linux-6.8.0-x86_64",
  "backend": "linux-x11",
  "read_only": false,
  "missing_tools": [],
  "screen": { "width": 1920, "height": 1080 },
  "cursor": { "x": 812, "y": 455 }
}
```

`missing_tools` is the thing to check first when input silently fails.

## `POST /screenshot`

```json
{ "region": [0, 0, 800, 600], "scale": 1400 }
```

Both fields optional: `region` is `[x, y, width, height]`, `scale` is a maximum
width in pixels (the agent downscales with ImageMagick or `sips` when
available). Responds `200` with `Content-Type: image/png` and the image bytes.

## `POST /input`

```json
{
  "actions": [
    { "type": "move",      "x": 100, "y": 200 },
    { "type": "click",     "x": 100, "y": 200, "button": "left", "count": 2 },
    { "type": "mousedown", "button": "left" },
    { "type": "mouseup",   "button": "left" },
    { "type": "drag",      "x": 10, "y": 10, "to_x": 200, "to_y": 300 },
    { "type": "scroll",    "dx": 0, "dy": -3 },
    { "type": "text",      "text": "typed literally" },
    { "type": "key",       "keys": ["ctrl+s", "enter"] },
    { "type": "sleep",     "ms": 250 }
  ]
}
```

Actions run in order; the response is `{"ok": true, "performed": N}`. At most 64
actions per request, `count` 1–5, `sleep` up to 5000 ms. A failing action stops
the batch — `performed` tells you how far it got, so re-screenshot rather than
assuming nothing happened.

`click` with `x`/`y` moves first. `button` is `left`, `right` or `middle`
(`middle` is unavailable on macOS). `dy` is positive for scrolling up.

## `GET /clipboard` and `POST /clipboard`

```json
{ "text": "clipboard contents" }
```

`GET` reads, `POST` writes. Writing is blocked in `--read-only` mode.

## Read-only mode

`remote_agentd.py --read-only` serves `/health`, `/screenshot` and
`GET /clipboard`, and answers `403` to `/input` and clipboard writes. Suggest it
whenever the user wants to watch a machine rather than drive it.

## Limits

Request bodies are capped at 4 MiB and each shelled-out tool call at 30 s. The
server is threaded, but the desktop is not: two callers driving the same mouse
will interleave badly. Run one controller at a time.

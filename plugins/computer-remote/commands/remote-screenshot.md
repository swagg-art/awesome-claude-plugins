---
description: Capture the remote screen and look at it
argument-hint: "[host] [--region x,y,w,h]"
allowed-tools: Bash(remotectl:*), Bash(python3:*), Read
---

Capture the remote desktop and describe what is on it.

Arguments: `$ARGUMENTS` — an optional host name and an optional
`--region x,y,w,h`.

1. Run `remotectl [--host HOST] screenshot --scale 1400 -o /tmp/remote-screen.png`,
   passing `--region` through if given.
2. Read the PNG with the Read tool.
3. Describe what is on screen: the focused window, what state it is in, and
   anything that blocks the user's next step (a dialog, a login prompt, an
   error). Note the screenshot is downscaled to 1400px wide — if you plan to
   click, say which full-resolution coordinates you would use.

Do not send input. This command only looks.

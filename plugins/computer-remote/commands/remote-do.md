---
description: Do something on the remote desktop, checking with a screenshot after each step
argument-hint: "<what to do on the remote machine>"
allowed-tools: Bash(remotectl:*), Bash(python3:*), Read
---

Carry out this on the remote desktop: **$ARGUMENTS**

Follow the `computer-remote` skill. In short:

1. `remotectl health` first — take the screen size from it, never assume one.
2. Screenshot, Read it, and locate the target by eye before any click. Scale
   coordinates back up if the screenshot was downscaled.
3. Act in small steps. Screenshot after each one and confirm it landed before
   the next.
4. Stop and ask the user before anything destructive or irreversible: closing
   unsaved work, sending a message, confirming a payment, deleting files,
   running an installer. It is their real machine.
5. Never type credentials. If a login is required, hand control back.

Report what you did and end with a final screenshot showing the result. If you
get stuck in a loop of failed clicks, stop and say what you see rather than
retrying a third time.

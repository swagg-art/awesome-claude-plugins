"""Terminal-style table rendering. No dependencies, no colour codes."""

from __future__ import annotations

NUMERIC = "0123456789.-+ "


def _fmt(value) -> str:
    """Floats default to 2dp; pass a preformatted string for prices."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _is_numeric(cells: list[str]) -> bool:
    seen = [c for c in cells if c not in ("", "-")]
    return bool(seen) and all(all(ch in NUMERIC for ch in c.replace(",", "")) for c in seen)


def render(headers: list[str], rows: list[list], title: str | None = None) -> str:
    """Render a box-drawn table. Numeric columns are right-aligned."""
    body = [[_fmt(cell) for cell in row] for row in rows]
    if not body:
        widths = [len(h) for h in headers]
    else:
        widths = [
            max(len(headers[i]), *(len(r[i]) for r in body)) for i in range(len(headers))
        ]
    right = [_is_numeric([r[i] for r in body]) for i in range(len(headers))]

    def line(left: str, mid: str, sep: str, end: str) -> str:
        return left + sep.join(mid * (w + 2) for w in widths) + end

    def row_text(cells: list[str], pad_right: list[bool]) -> str:
        out = []
        for i, cell in enumerate(cells):
            out.append(cell.rjust(widths[i]) if pad_right[i] else cell.ljust(widths[i]))
        return "│ " + " │ ".join(out) + " │"

    parts = []
    if title:
        parts.append(title)
    parts.append(line("┌", "─", "┬", "┐"))
    parts.append(row_text(headers, right))
    parts.append(line("├", "─", "┼", "┤"))
    for r in body:
        parts.append(row_text(r, right))
    if not body:
        span = sum(w + 2 for w in widths) + len(widths) - 1
        parts.append("│" + "(none)".center(span) + "│")
    parts.append(line("└", "─", "┴", "┘"))
    return "\n".join(parts)


def kv(pairs: list[tuple[str, object]], title: str | None = None) -> str:
    """Render label/value pairs as a two-column table."""
    return render(["Field", "Value"], [[k, v] for k, v in pairs], title)


def money(value: float, currency: str = "") -> str:
    sign = "-" if value < 0 else ""
    text = f"{sign}{abs(value):,.2f}"
    return f"{text} {currency}".strip()


def signed(value: float, digits: int = 2) -> str:
    return f"{value:+,.{digits}f}"

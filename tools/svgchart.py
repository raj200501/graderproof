#!/usr/bin/env python3
"""Deterministic SVG horizontal bar charts with optional interval whiskers (stdlib only).

tools/report.py draws the figures under docs/figures/ with :func:`horizontal_bars`.

Design: one series, so one neutral bar color and no legend (the title names what is
plotted); text in a neutral ink, never in the bar color; solid hairline gridlines; bars
14px thick (at most 24px) that grow from zero (the axis always includes 0), with a 4px
rounded data end and a square end at the baseline; the value printed at each bar's tip;
each bar carries a ``<title>`` tooltip. The background is transparent. An image cannot know
the page theme, so there is no ``prefers-color-scheme`` switch: every color is a mid-tone
gray that reads on light and dark pages. Ink ``#797979`` has WCAG contrast 4.35 on both
``#ffffff`` and ``#0d1117`` (the best one color can do on both); bars ``#8c8c8c`` reach at
least 3.3 on both. The part of a whisker that lies over its bar is drawn in ``#f5f5f5``
(contrast 3.1 with the bar) and the rest in the ink color.

Output depends only on the inputs: no timestamps or random ids (element ids derive from
``ident``), and every coordinate is rounded to two decimals.
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

INK = "#797979"
BAR = "#8c8c8c"
KNOCKOUT = "#f5f5f5"
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
WIDTH = 680
BAND = 30.0  # row height
THICKNESS = 14.0  # bar thickness
RADIUS = 4.0  # rounded data end
CAP = 10.0  # whisker cap height
MAX_LABEL = 40  # characters in a bar label
PLOT_TOP = 32.0


@dataclass(frozen=True)
class Bar:
    """One bar: a category label, its value, the printed value, and an optional interval."""

    label: str
    value: float
    value_text: str
    lo: float | None = None
    hi: float | None = None
    lo_text: str = ""
    hi_text: str = ""


def num(x: float) -> str:
    """A coordinate with at most two decimals and no trailing zeros."""
    text = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def esc(text: str) -> str:
    """Escape text for an SVG text node or attribute."""
    return html.escape(text, quote=True)


def text_width(text: str, size: float) -> float:
    """A generous estimate of rendered text width in a sans-serif face."""
    return len(text) * size * 0.6


def nice_step(span: float, target: int = 5) -> float:
    """A round tick step (1, 2, 2.5, or 5 times a power of ten) giving about ``target`` ticks."""
    if span <= 0 or not math.isfinite(span):
        raise ValueError("axis span must be positive and finite")
    raw = span / target
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 2.5, 5.0):
        if m * mag >= raw * (1 - 1e-9):
            return round(m * mag, 12)
    return round(10 * mag, 12)


def decimals(step: float) -> int:
    """Decimals needed to print multiples of ``step`` exactly."""
    exponent = Decimal(repr(step)).normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def ticks(lo: float, hi: float) -> list[float]:
    """Round tick positions within [lo, hi]."""
    step = nice_step(hi - lo)
    first = math.ceil(lo / step - 1e-9)
    out: list[float] = []
    k = first
    while k * step <= hi + step * 1e-9:
        out.append(round(k * step, 12))
        k += 1
    return out


def auto_domain(bars: Sequence[Bar]) -> tuple[float, float]:
    """An axis range that holds every value and interval end, including zero, on round ticks."""
    points = [0.0]
    for b in bars:
        points += [b.value] + [v for v in (b.lo, b.hi) if v is not None]
    lo, hi = min(points), max(points)
    if hi == lo:
        hi = lo + 1.0
    step = nice_step(hi - lo)
    low = math.floor(lo / step + 1e-9) * step
    high = math.ceil(hi / step - 1e-9) * step
    return round(low, 12), round(high, 12)


def tick_label(value: float, step: float, tick_format: str | None) -> str:
    """Text of one tick label."""
    text = tick_format.format(value) if tick_format else f"{value:.{decimals(step)}f}"
    if text.startswith("-") and not any(c in "123456789" for c in text):
        return text[1:]  # no negative zero
    return text


def bar_path(x0: float, x1: float, y: float, h: float) -> str:
    """A bar from baseline ``x0`` to data end ``x1``, rounded only at the data end."""
    r = min(RADIUS, abs(x1 - x0), h / 2)
    if x1 >= x0:
        return (
            f"M{num(x0)},{num(y)}H{num(x1 - r)}A{num(r)},{num(r)} 0 0 1 {num(x1)},{num(y + r)}"
            f"V{num(y + h - r)}A{num(r)},{num(r)} 0 0 1 {num(x1 - r)},{num(y + h)}H{num(x0)}Z"
        )
    return (
        f"M{num(x0)},{num(y)}H{num(x1 + r)}A{num(r)},{num(r)} 0 0 0 {num(x1)},{num(y + r)}"
        f"V{num(y + h - r)}A{num(r)},{num(r)} 0 0 0 {num(x1 + r)},{num(y + h)}H{num(x0)}Z"
    )


def whisker(xl: float, xh: float, y: float, span: tuple[float, float] | None) -> list[str]:
    """Interval line and caps; the parts over the bar ``span`` are drawn in the knockout color."""
    parts: list[tuple[float, float, str]] = []
    if span is None:
        parts.append((xl, xh, INK))
    else:
        a, b = span
        if xl < a:
            parts.append((xl, min(xh, a), INK))
        if max(xl, a) < min(xh, b):
            parts.append((max(xl, a), min(xh, b), KNOCKOUT))
        if xh > b:
            parts.append((max(xl, b), xh, INK))
    out = [
        f'<line x1="{num(p)}" y1="{num(y)}" x2="{num(q)}" y2="{num(y)}" stroke="{color}"/>'
        for p, q, color in parts
        if q > p
    ]
    for x in (xl, xh):
        inside = span is not None and span[0] + 0.5 < x < span[1] - 0.5
        color = KNOCKOUT if inside else INK
        out.append(
            f'<line x1="{num(x)}" y1="{num(y - CAP / 2)}" x2="{num(x)}" y2="{num(y + CAP / 2)}"'
            f' stroke="{color}"/>'
        )
    return out


def check_bars(bars: Sequence[Bar], domain: tuple[float, float] | None) -> None:
    """Raise ValueError for an empty chart, bad numbers, bad intervals, or bad labels."""
    if not bars:
        raise ValueError("a chart needs at least one bar")
    for b in bars:
        values = [b.value] + [v for v in (b.lo, b.hi) if v is not None]
        if not all(isinstance(v, int | float) and math.isfinite(v) for v in values):
            raise ValueError(f"bar {b.label!r}: values must be finite numbers")
        if (b.lo is None) != (b.hi is None):
            raise ValueError(f"bar {b.label!r}: give both interval ends or neither")
        if b.lo is not None and b.hi is not None and b.lo > b.hi:
            raise ValueError(f"bar {b.label!r}: interval low end is above its high end")
        if not b.label.strip() or len(b.label) > MAX_LABEL or "\n" in b.label:
            raise ValueError(f"bar label {b.label!r} must be 1 to {MAX_LABEL} characters")
        if domain is not None and not all(domain[0] <= v <= domain[1] for v in values):
            raise ValueError(f"bar {b.label!r}: a value lies outside the domain {list(domain)}")
    if domain is not None and not domain[0] < domain[1]:
        raise ValueError("domain must be [low, high] with low < high")
    if domain is not None and not domain[0] <= 0 <= domain[1]:
        raise ValueError("bars grow from zero, so the domain must include 0")


def horizontal_bars(
    ident: str,
    title: str,
    bars: Sequence[Bar],
    *,
    domain: tuple[float, float] | None = None,
    axis_label: str | None = None,
    tick_format: str | None = None,
    width: int = WIDTH,
) -> str:
    """An SVG document: one horizontal bar per entry, optional whiskers, a value at each tip."""
    check_bars(bars, domain)
    if not title.strip() or "\n" in title or text_width(title, 14) > width:
        raise ValueError(f"title {title!r} must be one line that fits the chart width")
    lo, hi = domain if domain is not None else auto_domain(bars)
    label_w = max(text_width(b.label, 12) for b in bars)
    value_w = max(text_width(b.value_text, 12) for b in bars)
    left = max(label_w + 16, 60.0)
    right = max(value_w + 14, 40.0)
    plot_w = width - left - right
    if plot_w < 120:
        raise ValueError("labels leave too little room for the plot; shorten them")
    plot_bottom = PLOT_TOP + BAND * len(bars)
    height = plot_bottom + (44 if axis_label else 26)

    def x(v: float) -> float:
        return left + (v - lo) / (hi - lo) * plot_w

    summaries = [
        f"{b.label}: {b.value_text}"
        + (f" (interval {b.lo_text} to {b.hi_text})" if b.lo is not None else "")
        for b in bars
    ]
    desc = "; ".join(summaries)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{num(height)}"'
        f' viewBox="0 0 {width} {num(height)}" role="img"'
        f' aria-labelledby="{esc(ident)}-title {esc(ident)}-desc" font-family="{esc(FONT)}">',
        f'<title id="{esc(ident)}-title">{esc(title)}</title>',
        f'<desc id="{esc(ident)}-desc">{esc(desc)}.</desc>',
        f'<text x="0" y="16" font-size="14" font-weight="600" fill="{INK}">{esc(title)}</text>',
        f'<g stroke="{INK}" stroke-width="1" stroke-opacity="0.3">',
    ]
    step = nice_step(hi - lo)
    tick_values = ticks(lo, hi)
    for t in tick_values:
        gx = math.floor(x(t)) + 0.5
        out.append(
            f'<line x1="{num(gx)}" y1="{num(PLOT_TOP)}" x2="{num(gx)}" y2="{num(plot_bottom)}"/>'
        )
    out.append("</g>")
    bx = math.floor(x(0.0)) + 0.5
    out.append(
        f'<line x1="{num(bx)}" y1="{num(PLOT_TOP)}" x2="{num(bx)}" y2="{num(plot_bottom)}"'
        f' stroke="{INK}" stroke-width="1" stroke-opacity="0.6"/>'
    )
    marks: list[str] = []
    texts: list[str] = []
    for i, b in enumerate(bars):
        cy = PLOT_TOP + BAND * (i + 0.5)
        x0, x1 = x(0.0), x(b.value)
        span = (min(x0, x1), max(x0, x1)) if abs(x1 - x0) >= 0.5 else None
        if span is not None:
            marks.append(
                f'<path d="{bar_path(x0, x1, cy - THICKNESS / 2, THICKNESS)}">'
                f"<title>{esc(summaries[i])}</title></path>"
            )
        tip = max(x0, x1)
        if b.lo is not None and b.hi is not None:
            marks += whisker(x(b.lo), x(b.hi), cy, span)
            tip = max(tip, x(b.hi))
        texts.append(
            f'<text x="{num(left - 10)}" y="{num(cy + 4)}" text-anchor="end">{esc(b.label)}</text>'
        )
        texts.append(f'<text x="{num(tip + 6)}" y="{num(cy + 4)}">{esc(b.value_text)}</text>')
    out.append(f'<g fill="{BAR}" stroke-width="1.5">')
    out += marks
    out.append("</g>")
    out.append(f'<g fill="{INK}" font-size="12">')
    out += texts
    out.append("</g>")
    out.append(
        f'<g fill="{INK}" font-size="11" text-anchor="middle"'
        ' style="font-variant-numeric: tabular-nums">'
    )
    out += [
        f'<text x="{num(x(t))}" y="{num(plot_bottom + 16)}">{esc(tick_label(t, step, tick_format))}'
        "</text>"
        for t in tick_values
    ]
    out.append("</g>")
    if axis_label:
        out.append(
            f'<text x="{num(left + plot_w / 2)}" y="{num(plot_bottom + 36)}" font-size="12"'
            f' text-anchor="middle" fill="{INK}">{esc(axis_label)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"

"""Tests for tools/svgchart.py: deterministic horizontal bar charts with interval whiskers."""

from __future__ import annotations

import re

import pytest
import svgchart
from svgchart import Bar

BARS = [
    Bar("HumanEval (synthetic)", 0.31, "0.31", 0.22, 0.41, "0.22", "0.41"),
    Bar("BFCL & friends", 0.08, "0.08", 0.03, 0.15, "0.03", "0.15"),
    Bar("Zero", 0.0, "0.00", 0.0, 0.06, "0.00", "0.06"),
    Bar("No interval", 0.55, "0.55"),
]


def chart(
    domain: tuple[float, float] | None = (0.0, 1.0),
    axis_label: str | None = "share",
    tick_format: str | None = "{:.0%}",
    width: int = svgchart.WIDTH,
) -> str:
    """The sample chart (synthetic values), with overrides."""
    return svgchart.horizontal_bars(
        "demo",
        "Synthetic rates",
        BARS,
        domain=domain,
        axis_label=axis_label,
        tick_format=tick_format,
        width=width,
    )


def stroke(element: str) -> str:
    """The stroke color of an SVG element."""
    return element.split('stroke="')[1][:7]


def test_num_esc_and_text_width() -> None:
    assert [svgchart.num(x) for x in (1.0, 1.234, -0.001, 0, 12.5, -3.456)] == [
        "1",
        "1.23",
        "0",
        "0",
        "12.5",
        "-3.46",
    ]
    assert svgchart.esc("<a & 'b'>") == "&lt;a &amp; &#x27;b&#x27;&gt;"
    assert svgchart.text_width("abcd", 10) == pytest.approx(24.0)


def test_nice_step_decimals_and_ticks() -> None:
    assert [svgchart.nice_step(s) for s in (1, 10, 0.3, 0.4, 7)] == [0.2, 2.0, 0.1, 0.1, 2.0]
    for bad in (0.0, -1.0, float("inf")):
        with pytest.raises(ValueError, match="positive and finite"):
            svgchart.nice_step(bad)
    assert [svgchart.decimals(s) for s in (0.2, 2.5, 10.0, 0.05, 1e-05)] == [1, 1, 0, 2, 5]
    assert svgchart.ticks(0, 1) == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert svgchart.ticks(-0.2, 0.2) == [-0.2, -0.1, 0.0, 0.1, 0.2]
    assert svgchart.ticks(0.05, 0.5) == [0.1, 0.2, 0.3, 0.4, 0.5]


def test_auto_domain_and_tick_label() -> None:
    assert svgchart.auto_domain([Bar("a", 0.1, "0.1", 0.05, 0.45)]) == (0.0, 0.5)
    assert svgchart.auto_domain([Bar("a", 0.0, "0")]) == (0.0, 1.0)
    negative = [Bar("a", -0.12, "-0.12", -0.2, -0.05), Bar("b", 0.07, "0.07")]
    assert svgchart.auto_domain(negative) == (-0.2, 0.1)
    assert svgchart.tick_label(0.2, 0.2, None) == "0.2"
    assert svgchart.tick_label(-0.0, 0.1, None) == "0.0"
    assert svgchart.tick_label(-0.1, 0.1, None) == "-0.1"
    assert svgchart.tick_label(0.4, 0.2, "{:.0%}") == "40%"
    assert svgchart.tick_label(-0.0, 0.2, "{:.0%}") == "0%"


def test_bar_path_rounds_only_the_data_end() -> None:
    assert svgchart.bar_path(10, 50, 5, 14) == "M10,5H46A4,4 0 0 1 50,9V15A4,4 0 0 1 46,19H10Z"
    assert svgchart.bar_path(50, 10, 5, 14) == "M50,5H14A4,4 0 0 0 10,9V15A4,4 0 0 0 14,19H50Z"
    assert svgchart.bar_path(10, 12, 5, 14) == "M10,5H10A2,2 0 0 1 12,7V17A2,2 0 0 1 10,19H10Z"


def test_whisker_knocks_out_the_part_over_the_bar() -> None:
    ink, knockout = svgchart.INK, svgchart.KNOCKOUT
    alone = svgchart.whisker(10, 50, 20, None)
    assert [stroke(w) for w in alone] == [ink] * 3
    left = svgchart.whisker(10, 50, 20, (0, 30))
    assert left[0] == f'<line x1="10" y1="20" x2="30" y2="20" stroke="{knockout}"/>'
    assert left[1] == f'<line x1="30" y1="20" x2="50" y2="20" stroke="{ink}"/>'
    middle = svgchart.whisker(10, 50, 20, (20, 60))
    assert [stroke(w) for w in middle] == [ink, knockout, ink, knockout]
    beyond = svgchart.whisker(60, 80, 20, (0, 50))  # an interval need not contain the bar end
    assert [stroke(w) for w in beyond] == [ink, ink, ink]
    inside = svgchart.whisker(10, 50, 20, (0, 80))
    assert all(knockout in w for w in inside) and len(inside) == 3


def test_check_bars_rejects_bad_input() -> None:
    cases: list[tuple[list[Bar], tuple[float, float] | None, str]] = [
        ([], None, "at least one bar"),
        ([Bar("a", float("nan"), "x")], None, "finite numbers"),
        ([Bar("a", 0.2, "0.2", 0.1)], None, "both interval ends"),
        ([Bar("a", 0.2, "0.2", 0.3, 0.1)], None, "low end is above its high end"),
        ([Bar(" ", 0.2, "0.2")], None, "must be 1 to 40 characters"),
        ([Bar("x" * 41, 0.2, "0.2")], None, "must be 1 to 40 characters"),
        ([Bar("a\nb", 0.2, "0.2")], None, "must be 1 to 40 characters"),
        ([Bar("a", 1.2, "1.2")], (0.0, 1.0), "outside the domain"),
        ([Bar("a", 0.2, "0.2")], (1.0, 1.0), "outside the domain"),
        ([Bar("a", 0.5, "0.5")], (0.5, 0.5), "low < high"),
        ([Bar("a", 0.6, "0.6")], (0.5, 1.0), "must include 0"),
    ]
    for bars, domain, message in cases:
        with pytest.raises(ValueError, match=message):
            svgchart.check_bars(bars, domain)
    svgchart.check_bars(BARS, (0.0, 1.0))


def test_horizontal_bars_document() -> None:
    svg = chart()
    assert svg == chart()  # deterministic
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="680" height="196"')
    assert svg.endswith("</svg>\n")
    assert 'role="img" aria-labelledby="demo-title demo-desc"' in svg
    assert '<title id="demo-title">Synthetic rates</title>' in svg
    assert "HumanEval (synthetic): 0.31 (interval 0.22 to 0.41); BFCL &amp; friends" in svg
    assert "<rect" not in svg and "background" not in svg  # transparent
    assert set(re.findall(r"#[0-9a-f]{6}", svg)) == {
        svgchart.INK,
        svgchart.BAR,
        svgchart.KNOCKOUT,
    }
    tooltips = re.findall(r"<path [^>]*><title>([^<]*)</title></path>", svg)
    assert tooltips == [
        "HumanEval (synthetic): 0.31 (interval 0.22 to 0.41)",
        "BFCL &amp; friends: 0.08 (interval 0.03 to 0.15)",
        "No interval: 0.55",
    ]  # the zero bar draws no path, only its whisker and labels
    assert [f">{v}<" in svg for v in ("0.31", "0.08", "0.00", "0.55")] == [True] * 4
    assert [f">{t}%<" in svg for t in (0, 20, 40, 60, 80, 100)] == [True] * 6
    assert ">share</text>" in svg


def test_horizontal_bars_layout_options() -> None:
    plain = chart(axis_label=None, tick_format=None)
    assert 'height="178"' in plain and ">share<" not in plain and ">0.2<" in plain
    auto = svgchart.horizontal_bars("auto", "Auto", [Bar("a", -0.12, "-0.12", -0.2, -0.05)])
    assert ">-0.20<" in auto and ">0.00<" in auto and ">-0.12<" in auto and "<path" in auto
    with pytest.raises(ValueError, match="too little room"):
        chart(width=200)
    with pytest.raises(ValueError, match="outside the domain"):
        chart(domain=(0.0, 0.5))
    for title in ("", "a\nb", "x" * 90):
        with pytest.raises(ValueError, match="must be one line"):
            svgchart.horizontal_bars("t", title, BARS)

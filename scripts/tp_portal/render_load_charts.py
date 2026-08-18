#!/usr/bin/env python3
"""Render two load-test reports (before/after) as one self-contained HTML page.

Consumes the JSON emitted by scripts/tp_portal/load_test.py (kind
"load-test-report") for the legacy monolith and the deployed estate, and
renders projector-friendly inline-SVG charts: latency percentiles side by
side, throughput and error/throttle rates, an optional per-second latency
curve (when either report carries a "timeseries" array of
{"t": <sec>, "p95_ms": <ms>} points), and an optional idle-cost comparison.
Stdlib only; the output opens from file:// or drops onto the hosted demo site.

Usage:
  python3 scripts/tp_portal/render_load_charts.py \
      --before load-monolith.json --after load-aws.json \
      --before-label "Legacy monolith (one VM)" --after-label "Serverless estate" \
      --vm-monthly-usd 70 --out load-comparison.html
"""
from __future__ import annotations

import argparse
import html
import json

BEFORE_COLOR = "#b3261e"
AFTER_COLOR = "#1a7f4b"

CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0;
       background: #f5f7fa; color: #1a2233; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 24px 32px 64px; }
h1 { font-size: 36px; margin: 16px 0 4px; }
.meta { font-size: 15px; color: #57637a; margin-bottom: 24px; }
.meta code { background: #e8ecf3; padding: 2px 6px; border-radius: 4px; }
.card { background: #fff; border-radius: 10px; padding: 20px 24px; margin-bottom: 24px;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.card h2 { margin: 0 0 4px; font-size: 22px; }
.card p.sub { margin: 0 0 12px; color: #57637a; font-size: 15px; }
.legend { font-size: 15px; margin-bottom: 8px; }
.legend span { display: inline-block; width: 14px; height: 14px; border-radius: 3px;
               margin: 0 6px 0 18px; vertical-align: -2px; }
.cost { display: flex; gap: 24px; font-size: 18px; }
.cost div { flex: 1; border-radius: 10px; padding: 18px; text-align: center; }
.cost .before { background: #fbdcda; } .cost .after { background: #d8f3e3; }
.cost strong { display: block; font-size: 34px; margin-top: 6px; }
"""


def bar_chart(pairs: list[tuple[str, float, float]], unit: str,
              lower_is_better: bool = True) -> str:
    """Grouped horizontal bars: (label, before, after) triples."""
    peak = max((max(b, a) for _, b, a in pairs), default=1) or 1
    width, bar_h, gap, label_w = 960, 30, 18, 190
    scale = (width - label_w - 130) / peak
    out, y = [], 8
    for label, before, after in pairs:
        for value, color in ((before, BEFORE_COLOR), (after, AFTER_COLOR)):
            out.append(
                f'<rect x="{label_w}" y="{y}" width="{max(2, value * scale):.1f}" '
                f'height="{bar_h}" rx="4" fill="{color}"/>'
                f'<text x="{label_w + max(2, value * scale) + 8:.1f}" y="{y + bar_h - 9}" '
                f'font-size="16">{value:g} {unit}</text>')
            y += bar_h + 6
        out.append(f'<text x="0" y="{y - bar_h - 14}" font-size="17" '
                   f'font-weight="600">{html.escape(label)}</text>')
        y += gap
    hint = ("lower is better" if lower_is_better else "higher is better")
    out.append(f'<text x="{width - 150}" y="{y - 4}" font-size="13" '
               f'fill="#57637a">{hint}</text>')
    return (f'<svg viewBox="0 0 {width} {y + 8}" width="100%" role="img" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg>')


def curve_chart(before: dict, after: dict, before_label: str, after_label: str) -> str:
    """Per-second p95 latency curves, when either report includes a timeseries."""
    series = [(r.get("timeseries") or [], color)
              for r, color in ((before, BEFORE_COLOR), (after, AFTER_COLOR))]
    if not any(points for points, _ in series):
        return ""
    width, height, pad = 960, 320, 50
    max_t = max((p["t"] for points, _ in series for p in points), default=1) or 1
    max_v = max((p["p95_ms"] for points, _ in series for p in points), default=1) or 1
    out = [f'<line x1="{pad}" y1="{height - pad}" x2="{width - 10}" y2="{height - pad}" stroke="#9aa4b5"/>',
           f'<line x1="{pad}" y1="10" x2="{pad}" y2="{height - pad}" stroke="#9aa4b5"/>',
           f'<text x="8" y="24" font-size="14" fill="#57637a">p95 ms</text>',
           f'<text x="{width - 90}" y="{height - 12}" font-size="14" fill="#57637a">seconds</text>']
    for points, color in series:
        if not points:
            continue
        coords = " ".join(
            f'{pad + p["t"] / max_t * (width - pad - 20):.1f},'
            f'{(height - pad) - p["p95_ms"] / max_v * (height - pad - 20):.1f}'
            for p in sorted(points, key=lambda p: p["t"]))
        out.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"/>')
    svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
           f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg>')
    return card("Latency under sustained load, second by second",
                f"{html.escape(before_label)} climbs as its thread pool saturates; "
                f"{html.escape(after_label)} stays flat by scaling out.", svg)


def card(title: str, sub: str, body: str) -> str:
    return (f'<div class="card"><h2>{html.escape(title)}</h2>'
            f'<p class="sub">{sub}</p>{body}</div>')


def render(before: dict, after: dict, args: argparse.Namespace) -> str:
    bl, al = args.before_label, args.after_label
    legend = (f'<p class="legend">Same pinned profile, both estates:'
              f'<span style="background:{BEFORE_COLOR}"></span>{html.escape(bl)}'
              f'<span style="background:{AFTER_COLOR}"></span>{html.escape(al)}</p>')
    lat = bar_chart([(p, before["latency_ms"][k], after["latency_ms"][k])
                     for p, k in (("p50 latency", "p50"), ("p95 latency", "p95"),
                                  ("p99 latency", "p99"))], "ms")
    thr = bar_chart([("Throughput", before["throughput_rps"], after["throughput_rps"])],
                    "req/s", lower_is_better=False)
    err = bar_chart([("Error rate", before["error_rate"] * 100, after["error_rate"] * 100),
                     ("Throttled (429, stage cap)", before.get("throttled_rate", 0) * 100,
                      after.get("throttled_rate", 0) * 100)], "%")
    profile = html.escape(before.get("profile", "?"))
    meta = (f'profile <code>{profile}</code> &middot; '
            f'{before.get("workers", "?")} workers &middot; '
            f'{before.get("duration_seconds", "?")}s per take')
    cost = ""
    if args.vm_monthly_usd is not None:
        cost = card(
            "What it costs when nobody is using it",
            "Every component of the migrated estate is per-request; the monolith's VM bills around the clock.",
            f'<div class="cost">'
            f'<div class="before">{html.escape(bl)}<strong>${args.vm_monthly_usd:g}/mo</strong>always-on VM</div>'
            f'<div class="after">{html.escape(al)}<strong>&asymp; $0/mo idle</strong>'
            f'{html.escape(args.serverless_cost_note)}</div></div>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(args.title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{html.escape(args.title)}</h1>
<p class="meta">{meta}</p>
{legend}
{card("Latency percentiles", "How long the same requests took, before and after.", lat)}
{curve_chart(before, after, bl, al)}
{card("Throughput", "Requests served per second under the same load.", thr)}
{card("Errors and throttling", "429s are the gateway stage cap, not service failures.", err)}
{cost}
</div></body></html>
"""


def load_report(path: str) -> dict:
    with open(path) as f:
        report = json.load(f)
    if report.get("kind") != "load-test-report":
        raise SystemExit(f"{path}: not a load-test-report (kind={report.get('kind')!r})")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--before", required=True, help="load report JSON for the legacy estate")
    p.add_argument("--after", required=True, help="load report JSON for the migrated estate")
    p.add_argument("--before-label", default="Legacy monolith")
    p.add_argument("--after-label", default="Serverless estate")
    p.add_argument("--title", default="Same load, both estates")
    p.add_argument("--vm-monthly-usd", type=float,
                   help="always-on monthly cost of the VM the monolith needs; "
                        "enables the idle-cost comparison card")
    p.add_argument("--serverless-cost-note", default="well under a cent per 1k requests",
                   help="per-request cost note for the after-state cost card")
    p.add_argument("--out", required=True, help="write the HTML page here")
    args = p.parse_args()

    before, after = load_report(args.before), load_report(args.after)
    if before.get("profile") != after.get("profile"):
        raise SystemExit(f"profile mismatch: {before.get('profile')!r} vs "
                         f"{after.get('profile')!r} — never compare different profiles")
    with open(args.out, "w") as f:
        f.write(render(before, after, args))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

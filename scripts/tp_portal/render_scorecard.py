#!/usr/bin/env python3
"""Render a recon report (*.recon.json) as a self-contained HTML scorecard.

Turns the machine-readable parity evidence (checks[], expected vs actual,
mismatches) into a projector-friendly page: one green/red banner, one row per
transcript step, and an expected-vs-actual diff for any failing step. Stdlib
only; the output embeds all CSS so it can be opened from file:// or dropped
onto the hosted demo site.

Usage:
  python3 scripts/tp_portal/render_scorecard.py \
      docs/tech-partnerships/recon/portal-decomposition-http-parity.recon.json \
      --out parity-scorecard.html

  # offline sample (includes one planted failure, for rehearsing the
  # "what a caught conversion mistake looks like" beat):
  python3 scripts/tp_portal/render_scorecard.py \
      scripts/tp_portal/samples/sample-parity.recon.json --out /tmp/sample.html
"""
from __future__ import annotations

import argparse
import html
import json

CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0;
       background: #f5f7fa; color: #1a2233; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 24px 32px 64px; }
.banner { border-radius: 12px; padding: 28px 32px; color: #fff; margin: 16px 0 28px; }
.banner.pass { background: #1a7f4b; } .banner.fail { background: #b3261e; }
.banner h1 { margin: 0 0 6px; font-size: 44px; }
.banner p { margin: 0; font-size: 20px; opacity: .92; }
.meta { font-size: 15px; color: #57637a; margin-bottom: 20px; }
.meta code { background: #e8ecf3; padding: 2px 6px; border-radius: 4px; }
table { width: 100%; border-collapse: collapse; background: #fff;
        border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
th { text-align: left; font-size: 14px; text-transform: uppercase; letter-spacing: .05em;
     color: #57637a; padding: 12px 16px; border-bottom: 2px solid #e2e7f0; }
td { padding: 12px 16px; border-bottom: 1px solid #eef1f6; font-size: 17px; }
td.step { font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.badge { display: inline-block; border-radius: 999px; padding: 4px 14px;
         font-size: 15px; font-weight: 600; }
.badge.pass { background: #d8f3e3; color: #14603a; }
.badge.fail { background: #fbdcda; color: #8f1d17; }
tr.failrow td { background: #fff6f5; }
.diff { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
.diff h4 { margin: 0 0 6px; font-size: 13px; text-transform: uppercase; color: #57637a; }
.diff pre { margin: 0; padding: 12px; border-radius: 8px; font-size: 14px;
            overflow-x: auto; background: #f1f4f9; }
.diff .actual pre { background: #fdeceb; }
.mismatches { margin: 10px 0 0; padding-left: 20px; color: #8f1d17; font-size: 15px; }
.footer { margin-top: 24px; font-size: 14px; color: #57637a; }
"""


def fmt_json(value: object) -> str:
    return html.escape(json.dumps(value, indent=2, sort_keys=True))


def check_row(check: dict) -> str:
    passed = check.get("result") == "pass"
    badge = f'<span class="badge {"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}</span>'
    step = html.escape(str(check.get("id", "?")))
    call = html.escape(f'{check.get("method", "?")} {check.get("path", "?")}')
    row = (f'<tr class="{"" if passed else "failrow"}">'
           f'<td class="step">{step}</td><td class="step">{call}</td><td>{badge}</td></tr>')
    if passed:
        return row
    mismatches = "".join(f"<li>{html.escape(str(m))}</li>" for m in check.get("mismatches", []))
    detail = (
        '<tr class="failrow"><td colspan="3">'
        f'<ul class="mismatches">{mismatches}</ul>'
        '<div class="diff">'
        f'<div><h4>Expected (golden transcript)</h4><pre>{fmt_json(check.get("expected"))}</pre></div>'
        f'<div class="actual"><h4>Actual (replayed)</h4><pre>{fmt_json(check.get("actual"))}</pre></div>'
        "</div></td></tr>"
    )
    return row + detail


def render(recon: dict, title: str | None) -> str:
    total = recon.get("steps_total", len(recon.get("checks", [])))
    passed = recon.get("steps_passed",
                       sum(1 for c in recon.get("checks", []) if c.get("result") == "pass"))
    all_pass = passed == total
    heading = title or f'Parity scorecard — {recon.get("unit", "recon report")}'
    verdict = "CONTRACT HOLDS" if all_pass else "CONVERSION MISTAKE CAUGHT"
    sub = (f"{passed} of {total} recorded behaviors replayed identically"
           if all_pass else
           f"{total - passed} of {total} behaviors diverged from the golden transcript — details below")
    meta_bits = []
    for label, key in (("namespace", "namespace"), ("run mode", "run_mode"),
                       ("generated", "generated_at"), ("replayed against", "replay_base_url")):
        if recon.get(key):
            meta_bits.append(f"{label} <code>{html.escape(str(recon[key]))}</code>")
    rows = "".join(check_row(c) for c in recon.get("checks", []))
    footer = ("Every row is one step of the golden HTTP transcript recorded against the legacy "
              "monolith and replayed against the migrated estate. Green means byte-for-byte "
              "contract parity; red shows exactly what the contract caught.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(heading)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<div class="banner {"pass" if all_pass else "fail"}"><h1>{verdict}</h1><p>{html.escape(sub)}</p></div>
<h2>{html.escape(heading)}</h2>
<p class="meta">{" &middot; ".join(meta_bits)}</p>
<table><thead><tr><th>Step</th><th>Request</th><th>Result</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="footer">{footer}</p>
</div></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("recon", help="path to a *.recon.json report with a checks[] array")
    p.add_argument("--out", required=True, help="write the HTML scorecard here")
    p.add_argument("--title", help="page heading (defaults to the recon's unit)")
    args = p.parse_args()

    with open(args.recon) as f:
        recon = json.load(f)
    if recon.get("kind") != "recon-report":
        raise SystemExit(f"{args.recon}: not a recon-report (kind={recon.get('kind')!r})")
    if not recon.get("checks"):
        raise SystemExit(f"{args.recon}: recon has no checks[] to render")

    with open(args.out, "w") as f:
        f.write(render(recon, args.title))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

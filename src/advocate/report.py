"""Report generation -- terminal output, JSON, and HTML."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Template

from advocate.models import Persona, Review, Severity
from advocate.personas import PERSONA_META


# ---- Terminal output ----


_SEV_COLORS = {
    Severity.critical: "\033[91;1m",  # bright red bold
    Severity.high: "\033[91m",        # red
    Severity.medium: "\033[93m",      # yellow
    Severity.low: "\033[90m",         # gray
    Severity.info: "\033[94m",        # blue
}
_RESET = "\033[0m"


def print_review(review: Review, color: bool = True) -> None:
    """Print review results to terminal."""

    def sev(s: Severity) -> str:
        if color:
            return f"{_SEV_COLORS.get(s, '')}{s.value:>8}{_RESET}"
        return f"{s.value:>8}"

    print(f"\n{'='*70}")
    print(f"  ADVOCATE REVIEW: {review.target}")
    print(f"  {review.total_findings} findings | ${review.total_cost_usd:.4f} | {len(review.persona_reports)} personas")
    print(f"{'='*70}\n")

    for report in review.persona_reports:
        meta = PERSONA_META[report.persona]
        header = f"  {meta['name']} — {meta['tagline']}"
        print(f"\033[1m{header}\033[0m" if color else header)
        print(f"  {'-'*len(header)}")

        if not report.findings:
            print(f"  No findings. (This is a strong positive signal.)\n")
        else:
            for f in sorted(report.findings, key=lambda x: list(Severity).index(x.severity)):
                print(f"  {sev(f.severity)} [{f.dimension.value}] {f.title}")
                if f.detail:
                    for line in f.detail.split("\n"):
                        print(f"             {line}")
                if f.recommendation:
                    print(f"          -> {f.recommendation}")
                print()

        if report.summary:
            print(f"  Summary: {report.summary[:200]}")
        print(f"  ({report.duration_ms:.0f}ms, ${report.estimated_cost_usd:.4f})\n")

    if review.disagreements:
        print(f"\033[1m  DISAGREEMENTS ({len(review.disagreements)})\033[0m" if color else
              f"  DISAGREEMENTS ({len(review.disagreements)})")
        print(f"  {'='*50}")
        for d in review.disagreements:
            print(f"  {d.tension}\n")


# ---- JSON output ----


def write_json(review: Review, path: Path) -> None:
    path.write_text(review.model_dump_json(indent=2))


# ---- HTML output ----

_HTML = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Advocate Review — {{ review.target }}</title>
<style>
  :root { --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff; --red: #f85149;
          --green: #3fb950; --yellow: #d29922; --border: #30363d; --card: #161b22; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--fg); line-height: 1.6; padding: 2rem; max-width: 1200px; margin: 0 auto; }
  h1 { color: var(--accent); margin-bottom: 0.25rem; }
  h2 { color: var(--fg); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin: 2rem 0 1rem; }
  h3 { margin: 1rem 0 0.5rem; }
  .meta { color: #8b949e; margin-bottom: 2rem; }
  .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; }
  .card .label { color: #8b949e; font-size: 0.85rem; text-transform: uppercase; }
  .card .value { font-size: 1.8rem; font-weight: 600; }
  .green { color: var(--green); } .red { color: var(--red); } .yellow { color: var(--yellow); }
  table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
  th { color: #8b949e; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
  .badge { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }
  .sev-critical { background: rgba(255,64,64,0.15); color: #ff4040; }
  .sev-high { background: rgba(248,81,73,0.15); color: var(--red); }
  .sev-medium { background: rgba(210,153,34,0.15); color: var(--yellow); }
  .sev-low { background: rgba(139,148,158,0.15); color: #8b949e; }
  .sev-info { background: rgba(88,166,255,0.15); color: var(--accent); }
  .persona-card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .persona-header { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.25rem; }
  .persona-tagline { color: #8b949e; font-style: italic; margin-bottom: 1rem; }
  .persona-summary { color: #8b949e; margin-top: 1rem; padding-top: 0.5rem; border-top: 1px solid var(--border); }
  .finding { margin: 0.5rem 0; padding: 0.5rem; border-left: 3px solid var(--border); }
  .finding-title { font-weight: 600; }
  .finding-detail { color: #8b949e; font-size: 0.9rem; margin-top: 0.25rem; }
  .finding-rec { color: var(--green); font-size: 0.9rem; margin-top: 0.25rem; }
  .tension { background: var(--card); border: 1px solid var(--yellow); border-radius: 6px; padding: 1rem; margin: 0.5rem 0; }
  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: #8b949e; font-size: 0.85rem; }
</style>
</head>
<body>

<h1>Advocate Review</h1>
<div class="meta">
  <strong>{{ review.target }}</strong> ({{ review.target_type }})<br>
  ID: {{ review.review_id }} | {{ review.started_at }}
</div>

<div class="summary-grid">
  <div class="card"><div class="label">Findings</div>
    <div class="value {{ 'red' if review.total_findings > 10 else 'yellow' if review.total_findings > 0 else 'green' }}">{{ review.total_findings }}</div></div>
  <div class="card"><div class="label">Personas</div><div class="value">{{ review.persona_reports|length }}</div></div>
  <div class="card"><div class="label">Disagreements</div>
    <div class="value {{ 'yellow' if review.disagreements else '' }}">{{ review.disagreements|length }}</div></div>
  <div class="card"><div class="label">Cost</div><div class="value">${{ "%.4f"|format(review.total_cost_usd) }}</div></div>
</div>

{% for report in review.persona_reports %}
<div class="persona-card">
  <div class="persona-header">{{ personas[report.persona.value].name }}</div>
  <div class="persona-tagline">{{ personas[report.persona.value].tagline }} — Success: {{ personas[report.persona.value].success }}</div>
  {% if not report.findings %}
  <p style="color: var(--green);">No findings. This is a strong positive signal from this persona.</p>
  {% endif %}
  {% for f in report.findings %}
  <div class="finding">
    <span class="badge sev-{{ f.severity.value }}">{{ f.severity.value }}</span>
    <span style="color:#8b949e;">[{{ f.dimension.value }}]</span>
    <span class="finding-title">{{ f.title }}</span>
    {% if f.detail %}<div class="finding-detail">{{ f.detail }}</div>{% endif %}
    {% if f.evidence %}<div class="finding-detail"><code>{{ f.evidence[:200] }}</code></div>{% endif %}
    {% if f.recommendation %}<div class="finding-rec">-> {{ f.recommendation }}</div>{% endif %}
  </div>
  {% endfor %}
  {% if report.summary %}
  <div class="persona-summary">{{ report.summary[:300] }}</div>
  {% endif %}
  <div style="color:#8b949e;font-size:0.8rem;margin-top:0.5rem;">{{ "%.0f"|format(report.duration_ms) }}ms | ${{ "%.4f"|format(report.estimated_cost_usd) }} | {{ report.input_tokens + report.output_tokens }} tokens</div>
</div>
{% endfor %}

{% if review.disagreements %}
<h2>Disagreements ({{ review.disagreements|length }})</h2>
<p style="color:#8b949e;margin-bottom:1rem;">When personas disagree, that's signal — it reveals tensions worth examining.</p>
{% for d in review.disagreements %}
<div class="tension">
  <p><span class="badge sev-{{ d.finding_a.severity.value }}">{{ d.finding_a.persona.value }}</span> {{ d.finding_a.title }}</p>
  <p style="margin:0.25rem 0;">vs</p>
  <p><span class="badge sev-{{ d.finding_b.severity.value }}">{{ d.finding_b.persona.value }}</span> {{ d.finding_b.title }}</p>
  <p style="color:var(--yellow);margin-top:0.5rem;">{{ d.tension }}</p>
</div>
{% endfor %}
{% endif %}

<footer>Generated by <strong>Advocate</strong> v{{ version }}</footer>
</body>
</html>
""")


def write_html(review: Review, path: Path) -> None:
    from advocate import __version__
    html = _HTML.render(
        review=review,
        personas={p.value: PERSONA_META[p] for p in Persona},
        version=__version__,
    )
    path.write_text(html)

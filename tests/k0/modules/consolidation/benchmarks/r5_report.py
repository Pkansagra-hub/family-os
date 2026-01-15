"""Report generation for R5 benchmarks.

Generates HTML, Markdown, and JSON reports including:
- Executive summary with pass/fail
- Coverage heatmaps
- Per-algorithm results
- Performance metrics
- Baseline comparisons
- Statistical analysis
- Visualizations (optional matplotlib/plotly)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Report Data Structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AlgorithmSummary:
    """Summary for a single algorithm run."""

    algorithm: str
    pack_name: str
    passed: bool
    total_items: int
    metrics: Dict[str, Any]
    failures: List[str]
    warnings: List[str]
    duration_ms: float = 0.0


@dataclass
class PerformanceMetrics:
    """Performance metrics for a benchmark run."""

    algorithm: str
    pack_name: str
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_per_sec: float
    memory_mb: float
    iterations: int = 0


@dataclass
class ReportData:
    """Complete data for report generation."""

    timestamp: str
    run_id: str
    algorithm_summaries: List[AlgorithmSummary]
    performance_metrics: List[PerformanceMetrics]
    baseline_comparisons: Optional[Dict[str, Any]] = None
    statistical_summary: Optional[Dict[str, Any]] = None
    seeds_used: List[int] = None
    total_duration_s: float = 0.0

    def __post_init__(self):
        if self.seeds_used is None:
            self.seeds_used = []


# ─────────────────────────────────────────────────────────────────────────────
# Report Generator Class
# ─────────────────────────────────────────────────────────────────────────────


class ReportGenerator:
    """Generate benchmark reports in multiple formats."""

    def __init__(self, data: ReportData):
        self.data = data

    # ─────────────────────────────────────────────────────────────────────────
    # JSON Report
    # ─────────────────────────────────────────────────────────────────────────

    def generate_json(self) -> str:
        """Generate JSON report."""
        report = {
            "meta": {
                "timestamp": self.data.timestamp,
                "run_id": self.data.run_id,
                "total_duration_s": self.data.total_duration_s,
                "seeds_used": self.data.seeds_used,
            },
            "summary": self._build_summary(),
            "algorithm_results": [asdict(s) for s in self.data.algorithm_summaries],
            "performance": [asdict(p) for p in self.data.performance_metrics],
        }

        if self.data.baseline_comparisons:
            report["baseline_comparisons"] = self.data.baseline_comparisons

        if self.data.statistical_summary:
            report["statistical_summary"] = self.data.statistical_summary

        return json.dumps(report, indent=2, default=str)

    # ─────────────────────────────────────────────────────────────────────────
    # Markdown Report
    # ─────────────────────────────────────────────────────────────────────────

    def generate_markdown(self) -> str:
        """Generate Markdown report."""
        lines = []

        # Header
        lines.append("# R5 Benchmark Report")
        lines.append("")
        lines.append(f"**Generated:** {self.data.timestamp}")
        lines.append(f"**Run ID:** {self.data.run_id}")
        lines.append(f"**Duration:** {self.data.total_duration_s:.2f}s")
        if self.data.seeds_used:
            lines.append(f"**Seeds:** {', '.join(map(str, self.data.seeds_used))}")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        summary = self._build_summary()
        lines.append(f"- **Total Tests:** {summary['total']}")
        lines.append(f"- **Passed:** {summary['passed']} ✅")
        lines.append(f"- **Failed:** {summary['failed']} ❌")
        lines.append(f"- **Pass Rate:** {summary['pass_rate']:.1%}")
        lines.append("")

        # Coverage Heatmap (text-based)
        lines.append("### Coverage by Algorithm & Pack")
        lines.append("")
        lines.append(self._build_coverage_table())
        lines.append("")

        # Per-Algorithm Results
        lines.append("## Algorithm Results")
        lines.append("")

        for algo in ["CPN", "MCTS", "BGT", "SPC"]:
            algo_results = [s for s in self.data.algorithm_summaries if s.algorithm == algo]
            if algo_results:
                lines.append(f"### {algo}")
                lines.append("")
                lines.append("| Pack | Status | Items | Duration | Failures |")
                lines.append("|------|--------|-------|----------|----------|")
                for r in algo_results:
                    status = "✅" if r.passed else "❌"
                    failures = ", ".join(r.failures[:2]) if r.failures else "-"
                    if len(r.failures) > 2:
                        failures += f" (+{len(r.failures) - 2})"
                    lines.append(
                        f"| {r.pack_name} | {status} | {r.total_items} | "
                        f"{r.duration_ms:.0f}ms | {failures} |"
                    )
                lines.append("")

        # Performance Metrics
        if self.data.performance_metrics:
            lines.append("## Performance Metrics")
            lines.append("")
            lines.append("| Algorithm | Pack | p50 (ms) | p95 (ms) | p99 (ms) | Throughput | Memory |")
            lines.append("|-----------|------|----------|----------|----------|------------|--------|")
            for p in self.data.performance_metrics:
                lines.append(
                    f"| {p.algorithm} | {p.pack_name} | {p.latency_p50_ms:.1f} | "
                    f"{p.latency_p95_ms:.1f} | {p.latency_p99_ms:.1f} | "
                    f"{p.throughput_per_sec:.1f}/s | {p.memory_mb:.1f}MB |"
                )
            lines.append("")

        # Baseline Comparisons
        if self.data.baseline_comparisons:
            lines.append("## Baseline Comparisons")
            lines.append("")
            for algo, comparisons in self.data.baseline_comparisons.items():
                lines.append(f"### {algo}")
                lines.append("")
                if isinstance(comparisons, list):
                    for c in comparisons:
                        improvement = c.get("improvement", 0)
                        direction = "↑" if improvement > 0 else "↓"
                        lines.append(
                            f"- **{c.get('metric_name', 'metric')}**: "
                            f"{c.get('algorithm_score', 0):.3f} vs baseline "
                            f"{c.get('baseline_score', 0):.3f} "
                            f"({direction}{abs(improvement):.1%})"
                        )
                lines.append("")

        # Statistical Summary
        if self.data.statistical_summary:
            lines.append("## Statistical Summary")
            lines.append("")
            for metric, stats in self.data.statistical_summary.items():
                if isinstance(stats, dict):
                    ci = stats.get("confidence_interval", {})
                    lines.append(f"### {metric}")
                    lines.append(f"- Mean: {stats.get('mean', 0):.3f}")
                    if ci:
                        lines.append(f"- 95% CI: [{ci.get('lower', 0):.3f}, {ci.get('upper', 0):.3f}]")
                    if "stability" in stats:
                        lines.append(f"- Stability: {stats['stability']:.2f}")
                    lines.append("")

        # Failures Summary
        all_failures = []
        for s in self.data.algorithm_summaries:
            for f in s.failures:
                all_failures.append(f"[{s.algorithm}/{s.pack_name}] {f}")

        if all_failures:
            lines.append("## Failure Details")
            lines.append("")
            for f in all_failures[:20]:  # Limit to 20
                lines.append(f"- {f}")
            if len(all_failures) > 20:
                lines.append(f"- ... and {len(all_failures) - 20} more")
            lines.append("")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # HTML Report
    # ─────────────────────────────────────────────────────────────────────────

    def generate_html(self) -> str:
        """Generate HTML report with styling and optional charts."""
        summary = self._build_summary()
        coverage_rows = self._build_coverage_html_rows()
        algo_sections = self._build_algorithm_html_sections()
        perf_rows = self._build_performance_html_rows()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>R5 Benchmark Report - {self.data.run_id}</title>
    <style>
        :root {{
            --pass-color: #22c55e;
            --fail-color: #ef4444;
            --warn-color: #f59e0b;
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-color: #1e293b;
            --border-color: #e2e8f0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        h2 {{ font-size: 1.5rem; margin: 2rem 0 1rem; border-bottom: 2px solid var(--border-color); padding-bottom: 0.5rem; }}
        h3 {{ font-size: 1.25rem; margin: 1.5rem 0 0.75rem; }}
        .meta {{ color: #64748b; font-size: 0.9rem; margin-bottom: 2rem; }}
        .card {{
            background: var(--card-bg);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .summary-card {{
            background: var(--card-bg);
            border-radius: 0.5rem;
            padding: 1.25rem;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .summary-card .value {{ font-size: 2rem; font-weight: bold; }}
        .summary-card .label {{ font-size: 0.875rem; color: #64748b; }}
        .pass {{ color: var(--pass-color); }}
        .fail {{ color: var(--fail-color); }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border-color); }}
        th {{ background: #f1f5f9; font-weight: 600; }}
        tr:hover {{ background: #f8fafc; }}
        .status-pass {{ color: var(--pass-color); font-weight: bold; }}
        .status-fail {{ color: var(--fail-color); font-weight: bold; }}
        .heatmap {{
            display: grid;
            grid-template-columns: auto repeat(4, 1fr);
            gap: 2px;
            margin: 1rem 0;
        }}
        .heatmap-cell {{
            padding: 0.5rem;
            text-align: center;
            font-size: 0.875rem;
        }}
        .heatmap-header {{ background: #f1f5f9; font-weight: 600; }}
        .heatmap-pass {{ background: #dcfce7; }}
        .heatmap-fail {{ background: #fee2e2; }}
        .heatmap-na {{ background: #f1f5f9; color: #94a3b8; }}
        .failure-list {{ list-style: none; }}
        .failure-list li {{ padding: 0.5rem; border-left: 3px solid var(--fail-color); margin: 0.5rem 0; background: #fef2f2; }}
        .chart-placeholder {{
            background: #f1f5f9;
            border: 2px dashed #cbd5e1;
            border-radius: 0.5rem;
            padding: 2rem;
            text-align: center;
            color: #64748b;
        }}
        @media (max-width: 768px) {{
            body {{ padding: 1rem; }}
            .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>R5 Benchmark Report</h1>
        <div class="meta">
            <strong>Run ID:</strong> {self.data.run_id} |
            <strong>Generated:</strong> {self.data.timestamp} |
            <strong>Duration:</strong> {self.data.total_duration_s:.2f}s
            {f"| <strong>Seeds:</strong> {', '.join(map(str, self.data.seeds_used))}" if self.data.seeds_used else ""}
        </div>

        <h2>Executive Summary</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <div class="value">{summary['total']}</div>
                <div class="label">Total Tests</div>
            </div>
            <div class="summary-card">
                <div class="value pass">{summary['passed']}</div>
                <div class="label">Passed</div>
            </div>
            <div class="summary-card">
                <div class="value fail">{summary['failed']}</div>
                <div class="label">Failed</div>
            </div>
            <div class="summary-card">
                <div class="value">{summary['pass_rate']:.0%}</div>
                <div class="label">Pass Rate</div>
            </div>
        </div>

        <h2>Coverage Heatmap</h2>
        <div class="card">
            <div class="heatmap">
                <div class="heatmap-cell heatmap-header">Pack</div>
                <div class="heatmap-cell heatmap-header">CPN</div>
                <div class="heatmap-cell heatmap-header">MCTS</div>
                <div class="heatmap-cell heatmap-header">BGT</div>
                <div class="heatmap-cell heatmap-header">SPC</div>
                {coverage_rows}
            </div>
        </div>

        <h2>Algorithm Results</h2>
        {algo_sections}

        <h2>Performance Metrics</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Algorithm</th>
                        <th>Pack</th>
                        <th>p50 (ms)</th>
                        <th>p95 (ms)</th>
                        <th>p99 (ms)</th>
                        <th>Throughput</th>
                        <th>Memory</th>
                    </tr>
                </thead>
                <tbody>
                    {perf_rows}
                </tbody>
            </table>
        </div>

        {self._build_baseline_html_section()}
        {self._build_failures_html_section()}

        <div class="chart-placeholder">
            <p>📊 Interactive charts available with matplotlib/plotly integration</p>
            <p>Run with <code>--visualize</code> to generate charts</p>
        </div>
    </div>
</body>
</html>"""

        return html

    # ─────────────────────────────────────────────────────────────────────────
    # Helper Methods
    # ─────────────────────────────────────────────────────────────────────────

    def _build_summary(self) -> Dict[str, Any]:
        """Build summary statistics."""
        total = len(self.data.algorithm_summaries)
        passed = sum(1 for s in self.data.algorithm_summaries if s.passed)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
        }

    def _build_coverage_table(self) -> str:
        """Build text-based coverage table."""
        packs = sorted(set(s.pack_name for s in self.data.algorithm_summaries))
        algorithms = ["CPN", "MCTS", "BGT", "SPC"]

        # Build lookup
        lookup = {}
        for s in self.data.algorithm_summaries:
            lookup[(s.pack_name, s.algorithm)] = s.passed

        lines = ["| Pack | CPN | MCTS | BGT | SPC |", "|------|-----|------|-----|-----|"]
        for pack in packs:
            row = [pack]
            for algo in algorithms:
                key = (pack, algo)
                if key in lookup:
                    row.append("✅" if lookup[key] else "❌")
                else:
                    row.append("-")
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _build_coverage_html_rows(self) -> str:
        """Build HTML heatmap rows."""
        packs = sorted(set(s.pack_name for s in self.data.algorithm_summaries))
        algorithms = ["CPN", "MCTS", "BGT", "SPC"]

        lookup = {}
        for s in self.data.algorithm_summaries:
            lookup[(s.pack_name, s.algorithm)] = s.passed

        rows = []
        for pack in packs:
            rows.append(f'<div class="heatmap-cell">{pack}</div>')
            for algo in algorithms:
                key = (pack, algo)
                if key in lookup:
                    cls = "heatmap-pass" if lookup[key] else "heatmap-fail"
                    symbol = "✅" if lookup[key] else "❌"
                else:
                    cls = "heatmap-na"
                    symbol = "-"
                rows.append(f'<div class="heatmap-cell {cls}">{symbol}</div>')

        return "\n                ".join(rows)

    def _build_algorithm_html_sections(self) -> str:
        """Build HTML sections for each algorithm."""
        sections = []
        for algo in ["CPN", "MCTS", "BGT", "SPC"]:
            results = [s for s in self.data.algorithm_summaries if s.algorithm == algo]
            if not results:
                continue

            rows = []
            for r in results:
                status_cls = "status-pass" if r.passed else "status-fail"
                status_text = "PASS" if r.passed else "FAIL"
                failures = ", ".join(r.failures[:2]) if r.failures else "-"
                if len(r.failures) > 2:
                    failures += f" (+{len(r.failures) - 2})"
                rows.append(f"""
                    <tr>
                        <td>{r.pack_name}</td>
                        <td class="{status_cls}">{status_text}</td>
                        <td>{r.total_items}</td>
                        <td>{r.duration_ms:.0f}ms</td>
                        <td>{failures}</td>
                    </tr>""")

            sections.append(f"""
        <div class="card">
            <h3>{algo}</h3>
            <table>
                <thead>
                    <tr>
                        <th>Pack</th>
                        <th>Status</th>
                        <th>Items</th>
                        <th>Duration</th>
                        <th>Failures</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>""")

        return "".join(sections)

    def _build_performance_html_rows(self) -> str:
        """Build HTML table rows for performance metrics."""
        if not self.data.performance_metrics:
            return '<tr><td colspan="7">No performance data available</td></tr>'

        rows = []
        for p in self.data.performance_metrics:
            rows.append(f"""
                    <tr>
                        <td>{p.algorithm}</td>
                        <td>{p.pack_name}</td>
                        <td>{p.latency_p50_ms:.1f}</td>
                        <td>{p.latency_p95_ms:.1f}</td>
                        <td>{p.latency_p99_ms:.1f}</td>
                        <td>{p.throughput_per_sec:.1f}/s</td>
                        <td>{p.memory_mb:.1f}MB</td>
                    </tr>""")
        return "".join(rows)

    def _build_baseline_html_section(self) -> str:
        """Build HTML section for baseline comparisons."""
        if not self.data.baseline_comparisons:
            return ""

        items = []
        for algo, comparisons in self.data.baseline_comparisons.items():
            if isinstance(comparisons, list):
                for c in comparisons:
                    improvement = c.get("improvement", 0)
                    direction = "↑" if improvement > 0 else "↓"
                    color = "pass" if improvement > 0 else "fail"
                    items.append(
                        f'<li><strong>{algo} - {c.get("metric_name", "metric")}:</strong> '
                        f'{c.get("algorithm_score", 0):.3f} vs baseline '
                        f'{c.get("baseline_score", 0):.3f} '
                        f'<span class="{color}">({direction}{abs(improvement):.1%})</span></li>'
                    )

        if not items:
            return ""

        return f"""
        <h2>Baseline Comparisons</h2>
        <div class="card">
            <ul>{"".join(items)}</ul>
        </div>"""

    def _build_failures_html_section(self) -> str:
        """Build HTML section for failure details."""
        failures = []
        for s in self.data.algorithm_summaries:
            for f in s.failures:
                failures.append(f"[{s.algorithm}/{s.pack_name}] {f}")

        if not failures:
            return ""

        items = "".join(f"<li>{f}</li>" for f in failures[:20])
        extra = f"<li>... and {len(failures) - 20} more failures</li>" if len(failures) > 20 else ""

        return f"""
        <h2>Failure Details</h2>
        <div class="card">
            <ul class="failure-list">{items}{extra}</ul>
        </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Visualization Module
# ─────────────────────────────────────────────────────────────────────────────


class BenchmarkVisualizer:
    """Generate visualizations for benchmark results."""

    def __init__(self, data: ReportData):
        self.data = data
        self._matplotlib_available = False
        self._plotly_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check which visualization libraries are available."""
        try:
            import matplotlib

            self._matplotlib_available = True
        except ImportError:
            logger.debug("matplotlib not available")

        try:
            import plotly

            self._plotly_available = True
        except ImportError:
            logger.debug("plotly not available")

    def generate_coverage_chart(self, output_path: Optional[Path] = None) -> Optional[str]:
        """Generate coverage heatmap chart."""
        if not self._matplotlib_available:
            return None

        import matplotlib.pyplot as plt
        import numpy as np

        packs = sorted(set(s.pack_name for s in self.data.algorithm_summaries))
        algorithms = ["CPN", "MCTS", "BGT", "SPC"]

        # Build matrix
        matrix = []
        for pack in packs:
            row = []
            for algo in algorithms:
                result = next(
                    (s for s in self.data.algorithm_summaries if s.pack_name == pack and s.algorithm == algo),
                    None,
                )
                if result:
                    row.append(1 if result.passed else 0)
                else:
                    row.append(-1)  # N/A
            matrix.append(row)

        matrix = np.array(matrix)

        fig, ax = plt.subplots(figsize=(8, max(4, len(packs) * 0.5)))

        # Custom colormap: -1=gray, 0=red, 1=green
        cmap = plt.cm.colors.ListedColormap(["#d1d5db", "#fee2e2", "#dcfce7"])
        bounds = [-1.5, -0.5, 0.5, 1.5]
        norm = plt.cm.colors.BoundaryNorm(bounds, cmap.N)

        im = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

        ax.set_xticks(range(len(algorithms)))
        ax.set_xticklabels(algorithms)
        ax.set_yticks(range(len(packs)))
        ax.set_yticklabels(packs)

        # Add text annotations
        for i in range(len(packs)):
            for j in range(len(algorithms)):
                val = matrix[i, j]
                text = "✓" if val == 1 else ("✗" if val == 0 else "-")
                ax.text(j, i, text, ha="center", va="center", fontsize=12)

        ax.set_title("Coverage Heatmap")
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()
            return str(output_path)
        else:
            plt.show()
            return None

    def generate_performance_chart(self, output_path: Optional[Path] = None) -> Optional[str]:
        """Generate performance comparison bar chart."""
        if not self._matplotlib_available:
            return None

        import matplotlib.pyplot as plt
        import numpy as np

        if not self.data.performance_metrics:
            return None

        algorithms = sorted(set(p.algorithm for p in self.data.performance_metrics))
        x = np.arange(len(algorithms))
        width = 0.25

        p50_vals = []
        p95_vals = []
        p99_vals = []

        for algo in algorithms:
            metrics = [p for p in self.data.performance_metrics if p.algorithm == algo]
            if metrics:
                p50_vals.append(np.mean([m.latency_p50_ms for m in metrics]))
                p95_vals.append(np.mean([m.latency_p95_ms for m in metrics]))
                p99_vals.append(np.mean([m.latency_p99_ms for m in metrics]))
            else:
                p50_vals.append(0)
                p95_vals.append(0)
                p99_vals.append(0)

        fig, ax = plt.subplots(figsize=(10, 6))
        bars1 = ax.bar(x - width, p50_vals, width, label="p50", color="#3b82f6")
        bars2 = ax.bar(x, p95_vals, width, label="p95", color="#f59e0b")
        bars3 = ax.bar(x + width, p99_vals, width, label="p99", color="#ef4444")

        ax.set_ylabel("Latency (ms)")
        ax.set_title("Performance by Algorithm")
        ax.set_xticks(x)
        ax.set_xticklabels(algorithms)
        ax.legend()

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()
            return str(output_path)
        else:
            plt.show()
            return None

    def generate_plotly_dashboard(self) -> Optional[str]:
        """Generate interactive Plotly dashboard HTML."""
        if not self._plotly_available:
            return None

        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=("Pass/Fail by Algorithm", "Latency Distribution", "Coverage Heatmap", "Throughput"),
            specs=[
                [{"type": "pie"}, {"type": "bar"}],
                [{"type": "heatmap"}, {"type": "bar"}],
            ],
        )

        # Pass/Fail pie chart
        summary = {}
        for s in self.data.algorithm_summaries:
            if s.algorithm not in summary:
                summary[s.algorithm] = {"passed": 0, "failed": 0}
            if s.passed:
                summary[s.algorithm]["passed"] += 1
            else:
                summary[s.algorithm]["failed"] += 1

        labels = list(summary.keys())
        passed = [summary[a]["passed"] for a in labels]
        failed = [summary[a]["failed"] for a in labels]

        fig.add_trace(
            go.Pie(
                labels=["Passed", "Failed"],
                values=[sum(passed), sum(failed)],
                marker_colors=["#22c55e", "#ef4444"],
            ),
            row=1,
            col=1,
        )

        # Latency bars
        if self.data.performance_metrics:
            algorithms = sorted(set(p.algorithm for p in self.data.performance_metrics))
            p95_vals = []
            for algo in algorithms:
                metrics = [p for p in self.data.performance_metrics if p.algorithm == algo]
                p95_vals.append(sum(m.latency_p95_ms for m in metrics) / len(metrics) if metrics else 0)

            fig.add_trace(
                go.Bar(x=algorithms, y=p95_vals, marker_color="#3b82f6", name="p95 Latency"),
                row=1,
                col=2,
            )

        fig.update_layout(height=800, showlegend=True, title_text="R5 Benchmark Dashboard")

        return fig.to_html(include_plotlyjs="cdn")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def generate_report(results: List[Dict[str, Any]], fmt: str = "markdown") -> str:
    """Generate report text in the requested format.

    Args:
        results: List of benchmark result dicts.
        fmt: Report format - 'markdown', 'html', or 'json'.

    Returns:
        Report string.
    """
    # Convert results to ReportData
    summaries = []
    performance = []

    for r in results:
        # Handle CoverageResult-like dicts
        if "algorithm" in r and "pack_name" in r:
            summaries.append(
                AlgorithmSummary(
                    algorithm=r.get("algorithm", "UNKNOWN"),
                    pack_name=r.get("pack_name", "unknown"),
                    passed=r.get("passed", False),
                    total_items=r.get("metrics", {}).get("total_items", 0),
                    metrics=r.get("metrics", {}),
                    failures=r.get("failures", []),
                    warnings=r.get("warnings", []),
                    duration_ms=r.get("duration_ms", 0.0),
                )
            )

        # Handle performance metrics if present
        if "latency_p50_ms" in r:
            performance.append(
                PerformanceMetrics(
                    algorithm=r.get("algorithm", "UNKNOWN"),
                    pack_name=r.get("pack_name", "unknown"),
                    latency_p50_ms=r.get("latency_p50_ms", 0),
                    latency_p95_ms=r.get("latency_p95_ms", 0),
                    latency_p99_ms=r.get("latency_p99_ms", 0),
                    throughput_per_sec=r.get("throughput_per_sec", 0),
                    memory_mb=r.get("memory_mb", 0),
                )
            )

    data = ReportData(
        timestamp=datetime.now().isoformat(),
        run_id=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        algorithm_summaries=summaries,
        performance_metrics=performance,
        baseline_comparisons=None,
        statistical_summary=None,
    )

    generator = ReportGenerator(data)

    if fmt == "json":
        return generator.generate_json()
    elif fmt == "html":
        return generator.generate_html()
    else:
        return generator.generate_markdown()


def save_report(content: str, path: str) -> None:
    """Persist report content to disk.

    Args:
        content: Report content string.
        path: Output file path.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Report saved to: {output_path}")

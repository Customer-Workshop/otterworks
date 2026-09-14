"""Render the fixed-layout P1 OW_BILLING monthly-invoicing lineage DAG."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle
import networkx as nx


REPO = Path("/home/ubuntu/repos/otterworks")
LINEAGE = REPO / ".migration/evidence/census/lineage_edges.tsv"
OUTPUT = REPO / "docs/migration/P1_monthly_invoicing_dag.png"

TABLES = {
    "CODES",
    "PLANS",
    "TENANTS",
    "BILLING_AUDIT_LOG",
    "SUBSCRIPTIONS",
    "SUBSCRIPTIONS_HIST",
    "USAGE_EVENTS",
    "RATING_PERIODS",
    "RATING_RESULTS",
    "INVOICES",
    "INVOICE_LINES",
    "CREDIT_NOTES",
}
ANALYTICAL = {"SUBSCRIPTIONS_HIST"}
PACKAGES = {"PKG_OW_UTIL", "PKG_PLANS", "PKG_RATING", "PKG_INVOICING"}
TRIGGERS = {
    "TRG_BILLING_AUDIT_LOG_ID",
    "TRG_SUBSCRIPTIONS_HIST",
    "TRG_SUB_NO_UNCANCEL",
    "TRG_USAGE_EVENTS_CHECK",
}
EXTERNALS = {
    "Billing service",
    "Monthly scheduler",
    "Usage-ingestion service",
}
NODES = TABLES | PACKAGES | TRIGGERS
ALL_NODES = NODES | EXTERNALS

UNITS = {
    "U0 shared": ["CODES", "PLANS", "TENANTS", "BILLING_AUDIT_LOG", "PKG_OW_UTIL", "TRG_BILLING_AUDIT_LOG_ID"],
    "U1": ["SUBSCRIPTIONS", "SUBSCRIPTIONS_HIST", "TRG_SUBSCRIPTIONS_HIST", "TRG_SUB_NO_UNCANCEL", "PKG_PLANS"],
    "U2": ["USAGE_EVENTS", "TRG_USAGE_EVENTS_CHECK"],
    "U3": ["RATING_PERIODS", "RATING_RESULTS", "PKG_RATING"],
    "U4": ["INVOICES", "INVOICE_LINES", "CREDIT_NOTES", "PKG_INVOICING"],
}

COLORS = {
    "operational": "#8fd18f",
    "analytical": "#8fb8f0",
    "package": "#f2c66d",
    "trigger": "#e0a0e0",
    "external": "#d0d0d0",
}
EDGE_STYLES = {
    "write": ("#c62828", "solid"),
    "read": ("#666666", "dashed"),
    "fk": ("#222222", "solid"),
    "trg": ("#7b1fa2", "dotted"),
    "call": ("#ef8c00", "solid"),
}


def node_color(node: str) -> str:
    if node in EXTERNALS:
        return COLORS["external"]
    if node in TRIGGERS:
        return COLORS["trigger"]
    if node in PACKAGES:
        return COLORS["package"]
    if node in ANALYTICAL:
        return COLORS["analytical"]
    return COLORS["operational"]


def read_edges() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    with LINEAGE.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    kept = [row for row in rows if row["SRC"] in NODES and row["DST"] in NODES]
    dropped = [row for row in rows if (row["SRC"] in NODES) != (row["DST"] in NODES)]
    return kept, dropped


def add_edge(graph: nx.DiGraph, source: str, target: str, kind: str, mark: str) -> None:
    graph.add_edge(source, target, kind=kind, mark=mark, external=False)


def build_graph() -> tuple[nx.DiGraph, list[dict[str, str]]]:
    kept, dropped = read_edges()
    graph = nx.DiGraph()
    graph.add_nodes_from(ALL_NODES)
    for row in kept:
        add_edge(graph, row["SRC"], row["DST"], row["KIND"], row["MARK"])

    for package in ("PKG_PLANS", "PKG_RATING", "PKG_INVOICING"):
        graph.add_edge("Billing service", package, kind="call", mark="INTENDED", external=True)
    graph.add_edge("Monthly scheduler", "Billing service", kind="call", mark="INTENDED", external=True)
    graph.add_edge("Usage-ingestion service", "USAGE_EVENTS", kind="write", mark="INTENDED", external=True)
    graph.add_edge("PKG_INVOICING", "PKG_RATING", kind="call", mark="INTENDED", external=False)
    return graph, dropped


def layout() -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    unit_x = {"U0 shared": 0.0, "U1": 4.4, "U2": 8.8, "U3": 13.2, "U4": 17.6}
    y_values = {
        "U0 shared": [4.1, 2.8, 1.5, 0.2, -1.1, -2.4],
        "U1": [2.8, 1.5, 0.2, -1.1, -2.4],
        "U2": [1.8, 0.4],
        "U3": [2.4, 1.1, -0.2],
        "U4": [2.6, 1.2, -0.2, -1.6],
    }
    for unit, nodes in UNITS.items():
        positions.update({node: (unit_x[unit], y) for node, y in zip(nodes, y_values[unit])})
    positions.update(
        {
            "Monthly scheduler": (4.4, 6.8),
            "Billing service": (9.8, 6.8),
            "Usage-ingestion service": (15.2, 6.8),
        }
    )
    return positions


def draw_group_boxes(ax: plt.Axes) -> None:
    unit_x = {"U0 shared": 0.0, "U1": 4.4, "U2": 8.8, "U3": 13.2, "U4": 17.6}
    heights = {"U0 shared": 7.4, "U1": 6.2, "U2": 4.2, "U3": 5.0, "U4": 5.4}
    bottoms = {"U0 shared": -3.0, "U1": -3.0, "U2": -0.3, "U3": -0.9, "U4": -2.3}
    for unit, x in unit_x.items():
        ax.add_patch(
            Rectangle(
                (x - 1.45, bottoms[unit]),
                2.9,
                heights[unit],
                fill=False,
                edgecolor="#8a8a8a",
                linewidth=1.0,
                linestyle="--" if unit == "U0 shared" else "-",
                zorder=0,
            )
        )
        ax.text(
            x - 1.3,
            bottoms[unit] + heights[unit] - 0.18,
            unit,
            color="#555555",
            fontsize=9,
            fontweight="bold",
            va="top",
            zorder=1,
        )


def draw_graph(graph: nx.DiGraph) -> None:
    positions = layout()
    fig, ax = plt.subplots(figsize=(23, 12))
    draw_group_boxes(ax)

    labels = {
        node: f"{node}\n(intended, unnamed)" if node in EXTERNALS else node
        for node in graph.nodes
    }
    nx.draw_networkx_nodes(
        graph,
        positions,
        node_color=[node_color(node) for node in graph.nodes],
        node_size=[2900 if node in EXTERNALS else 2450 for node in graph.nodes],
        node_shape="o",
        edgecolors=["#555555" if node in EXTERNALS else "#333333" for node in graph.nodes],
        linewidths=1.0,
        ax=ax,
    )
    nx.draw_networkx_labels(graph, positions, labels=labels, font_size=8, ax=ax)

    for edge, attributes in graph.edges.items():
        source, target = edge
        kind = attributes["kind"]
        external = attributes["external"]
        color, style = EDGE_STYLES[kind]
        if external:
            color, style = "#777777", "dashed"
        nx.draw_networkx_edges(
            graph,
            positions,
            edgelist=[edge],
            edge_color=color,
            style=style,
            width=1.2 if not external else 1.0,
            arrows=True,
            arrowsize=15,
            connectionstyle="arc3,rad=0.035",
            ax=ax,
        )

    legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["operational"], markeredgecolor="#333333", label="Operational table", markersize=10),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["analytical"], markeredgecolor="#333333", label="Analytical table", markersize=10),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["package"], markeredgecolor="#333333", label="Package", markersize=10),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["trigger"], markeredgecolor="#333333", label="Trigger", markersize=10),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["external"], markeredgecolor="#555555", label="External (intended, unnamed)", markersize=10),
        Line2D([0], [0], color="#c62828", linestyle="solid", label="Write"),
        Line2D([0], [0], color="#666666", linestyle="dashed", label="Read"),
        Line2D([0], [0], color="#222222", linestyle="solid", label="FK"),
        Line2D([0], [0], color="#7b1fa2", linestyle="dotted", label="Trigger"),
        Line2D([0], [0], color="#ef8c00", linestyle="solid", label="Call"),
        Line2D([0], [0], color="#777777", linestyle="dashed", label="External edge"),
    ]
    ax.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.055), ncol=6, fontsize=8, frameon=False)
    ax.set_title("P1 Monthly invoicing — unit DAG (OW_BILLING)", fontsize=16, pad=16)
    ax.set_xlim(-2.2, 19.8)
    ax.set_ylim(-3.45, 7.55)
    ax.axis("off")
    fig.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    graph, dropped = build_graph()
    draw_graph(graph)
    print(f"Rendered {OUTPUT}")
    print(f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"Dropped {len(dropped)} lineage_edges.tsv rows touching the node set:")
    for row in dropped:
        print(f"  {row['SRC']} -> {row['DST']} [{row['KIND']}, {row['MARK']}]")


if __name__ == "__main__":
    main()

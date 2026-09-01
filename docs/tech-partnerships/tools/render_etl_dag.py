#!/usr/bin/env python3
"""Render the legacy ETL estate lineage DAG (inventory artifact).

Usage: python3 docs/tech-partnerships/tools/render_etl_dag.py docs/tech-partnerships/OtterWorks_ETL_dag.png
Solid edges are FACT (cited in OtterWorks_ETL_inventory.md), dashed edges are INFERRED.
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

JOBS = {
    "analytics_daily.py": "P-A",
    "user_activity_daily.py": "P-A",
    "sftp_ingest_poll.ksh": "P-B",
    "parse_custbill_fixedwidth.sh": "P-B",
    "finance_excel_report.pl": "P-B",
    "run_all.sh": "P-B",
    "audit_archive_weekly.py": "P-C",
    "storage_cleanup_daily.py": "P-D",
    "search_reindex_weekly.py": "P-E",
}
STORES = [
    "SQS otterworks-analytics", "DDB otterworks-analytics-events",
    "S3 data-lake analytics/daily/*", "PG analytics_daily_summary",
    "S3 data-lake reports/user-activity/*", "admin-service (INFERRED)",
    "SFTP drop CUSTBILL*.dat", "incoming/CUSTBILL*.dat", "parsed/CUSTBILL*.psv",
    "reports/finance_billing_*.csv/.xls", "finance-reports@ (sendmail no-op)",
    "DDB otterworks-audit-events", "S3 archive audit-archive/* (GLACIER)",
    "S3 file-storage files/*", "DDB otterworks-file-metadata", "S3 quarantine quarantined/*",
    "document-service /api/v1/documents", "file-service /api/v1/files",
    "MeiliSearch documents+files", "search-service",
]
FACT = [
    ("SQS otterworks-analytics", "analytics_daily.py"),
    ("DDB otterworks-analytics-events", "analytics_daily.py"),
    ("analytics_daily.py", "S3 data-lake analytics/daily/*"),
    ("analytics_daily.py", "PG analytics_daily_summary"),
    ("S3 data-lake analytics/daily/*", "user_activity_daily.py"),
    ("PG analytics_daily_summary", "user_activity_daily.py"),
    ("user_activity_daily.py", "S3 data-lake reports/user-activity/*"),
    ("SFTP drop CUSTBILL*.dat", "sftp_ingest_poll.ksh"),
    ("sftp_ingest_poll.ksh", "incoming/CUSTBILL*.dat"),
    ("incoming/CUSTBILL*.dat", "parse_custbill_fixedwidth.sh"),
    ("parse_custbill_fixedwidth.sh", "parsed/CUSTBILL*.psv"),
    ("parsed/CUSTBILL*.psv", "finance_excel_report.pl"),
    ("finance_excel_report.pl", "reports/finance_billing_*.csv/.xls"),
    ("finance_excel_report.pl", "finance-reports@ (sendmail no-op)"),
    ("run_all.sh", "sftp_ingest_poll.ksh"),
    ("run_all.sh", "parse_custbill_fixedwidth.sh"),
    ("run_all.sh", "finance_excel_report.pl"),
    ("DDB otterworks-audit-events", "audit_archive_weekly.py"),
    ("audit_archive_weekly.py", "S3 archive audit-archive/* (GLACIER)"),
    ("S3 file-storage files/*", "storage_cleanup_daily.py"),
    ("DDB otterworks-file-metadata", "storage_cleanup_daily.py"),
    ("storage_cleanup_daily.py", "S3 quarantine quarantined/*"),
    ("document-service /api/v1/documents", "search_reindex_weekly.py"),
    ("file-service /api/v1/files", "search_reindex_weekly.py"),
    ("search_reindex_weekly.py", "MeiliSearch documents+files"),
    ("MeiliSearch documents+files", "search-service"),
]
INFERRED = [("S3 data-lake reports/user-activity/*", "admin-service (INFERRED)")]
COLORS = {"P-A": "#4c72b0", "P-B": "#dd8452", "P-C": "#55a868", "P-D": "#c44e52", "P-E": "#8172b3"}


def main(out: str) -> None:
    g = nx.DiGraph()
    g.add_edges_from(FACT + INFERRED)
    for layer, nodes in enumerate(nx.topological_generations(g)):
        for n in nodes:
            g.nodes[n]["layer"] = layer
    band = {}
    for j, p in JOBS.items():
        band[j] = p
        for a, b in FACT + INFERRED:
            if a == j and b not in JOBS:
                band.setdefault(b, p)
            if b == j and a not in JOBS:
                band.setdefault(a, p)
    band["MeiliSearch documents+files"] = band["search-service"] = "P-E"
    band["admin-service (INFERRED)"] = "P-A"
    order = ["P-A", "P-B", "P-C", "P-D", "P-E"]
    pos, used = {}, {}
    for n in g:
        col, row = g.nodes[n]["layer"], order.index(band[n])
        k = used.get((col, row), 0)
        used[(col, row)] = k + 1
        pos[n] = (col * 3.0, -(row * 4.0 + k * 1.1))
    plt.figure(figsize=(22, 13))
    job_nodes = [n for n in g if n in JOBS]
    store_nodes = [n for n in g if n not in JOBS]
    nx.draw_networkx_nodes(g, pos, nodelist=job_nodes, node_shape="s", node_size=3200,
                           node_color=[COLORS[JOBS[n]] for n in job_nodes])
    nx.draw_networkx_nodes(g, pos, nodelist=store_nodes, node_shape="o", node_size=2200, node_color="#dddddd")
    nx.draw_networkx_edges(g, pos, edgelist=FACT, arrows=True, arrowsize=18, width=1.4)
    nx.draw_networkx_edges(g, pos, edgelist=INFERRED, arrows=True, arrowsize=18, width=1.4, style="dashed",
                           edge_color="#999999")
    nx.draw_networkx_labels(g, pos, font_size=7)
    plt.title("OtterWorks legacy ETL estate — lineage DAG (squares = jobs coloured by pipeline; "
              "solid = FACT, dashed = INFERRED)")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out, dpi=110)


if __name__ == "__main__":
    main(sys.argv[1])

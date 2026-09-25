package com.otterworks.report.reconciliation;

import com.otterworks.report.reconciliation.ReconciliationReport.ClassTotalRow;
import com.otterworks.report.reconciliation.ReconciliationReport.FailureRow;
import com.otterworks.report.reconciliation.ReconciliationReport.SessionLink;
import com.otterworks.report.reconciliation.ReconciliationReport.TableRow;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Standalone HTML page for one reconciliation run: summary table, closes badge, class totals
 * (MIG-07 rows highlighted), failed rows and session links. Rendered server-side with no
 * template engine so the Java 8 service gains no new runtime dependency.
 */
public final class ReconciliationHtmlRenderer {

    static final String MIG07 = "MIG-07";

    private ReconciliationHtmlRenderer() {
    }

    public static String render(ReconciliationReport report) {
        StringBuilder html = new StringBuilder(8192);
        html.append("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n")
            .append("<title>Reconciliation ").append(esc(report.runId)).append("</title>\n")
            .append("<style>\n").append(css()).append("</style>\n</head>\n<body>\n");

        html.append("<header>\n<h1>Reconciliation report <code>").append(esc(report.runId)).append("</code></h1>\n")
            .append("<p class=\"meta\">namespace <code>").append(esc(report.namespace)).append("</code>")
            .append(" &middot; status ").append(esc(report.status))
            .append(" &middot; started ").append(esc(report.startedAt))
            .append(" &middot; finished ").append(esc(nvl(report.finishedAt, "-")))
            .append(" &middot; generated ").append(esc(report.generatedAt)).append("</p>\n")
            .append(report.closes
                ? "<p class=\"badge ok\">CLOSES: extracted = loaded + rejected and purged = validated</p>\n"
                : "<p class=\"badge fail\">DOES NOT CLOSE</p>\n")
            .append("<p class=\"links\"><a href=\"").append(esc(report.runId)).append(".csv\">Download CSV</a>")
            .append(" &middot; <a href=\"").append(esc(report.runId)).append("\">JSON</a></p>\n</header>\n");

        renderSummary(html, report);
        renderClassTotals(html, report);
        renderFailures(html, report);
        renderSessions(html, report);

        html.append("</body>\n</html>\n");
        return html.toString();
    }

    private static void renderSummary(StringBuilder html, ReconciliationReport report) {
        html.append("<section>\n<h2>Summary (one row per source table)</h2>\n<table>\n<thead><tr>")
            .append("<th>table</th><th>extracted</th><th>loaded</th><th>validated</th><th>purged</th>")
            .append("<th>failed</th><th>rejected (LOAD)</th><th>validate failed</th><th>purge intended</th>")
            .append("<th>dry run</th><th>closes</th></tr></thead>\n<tbody>\n");
        for (TableRow row : report.tables) {
            html.append("<tr class=\"").append(row.closes ? "closes" : "open").append("\">")
                .append("<td>").append(esc(row.table)).append("</td>")
                .append(num(row.extracted)).append(num(row.loaded)).append(num(row.validated))
                .append(num(row.purged)).append(num(row.failed)).append(num(row.rejected))
                .append(num(row.validateFailed)).append(num(row.purgeIntended))
                .append("<td>").append(row.purgeDryRun == null ? "-" : row.purgeDryRun ? "yes" : "no").append("</td>")
                .append("<td>").append(row.closes ? "yes" : "no").append("</td></tr>\n");
        }
        html.append("</tbody>\n</table>\n</section>\n");
    }

    private static void renderClassTotals(StringBuilder html, ReconciliationReport report) {
        html.append("<section>\n<h2>Per-class totals (MIG-07 evidence)</h2>\n")
            .append("<p class=\"note\">Table-level storage-charge totals alone never pass: each retention class ")
            .append("must agree in row count and in charge sum to the eighth decimal. Highlighted rows differ.</p>\n");
        if (report.classTotals.isEmpty()) {
            html.append("<p class=\"empty\">No class totals recorded for this run.</p>\n</section>\n");
            return;
        }
        html.append("<table>\n<thead><tr><th>table</th><th>class</th><th>source count</th><th>target count</th>")
            .append("<th>source sum</th><th>target sum</th><th>result</th></tr></thead>\n<tbody>\n");
        for (ClassTotalRow row : report.classTotals) {
            html.append("<tr class=\"").append(row.matches ? "match" : "mig07").append("\">")
                .append("<td>").append(esc(row.table)).append("</td>")
                .append("<td>").append(esc(row.retentionClass)).append("</td>")
                .append(num(row.sourceCount)).append(num(row.targetCount))
                .append("<td class=\"num\">").append(esc(nvl(row.sourceSum, "-"))).append("</td>")
                .append("<td class=\"num\">").append(esc(nvl(row.targetSum, "-"))).append("</td>")
                .append("<td>").append(row.matches ? "match" : "<strong>" + MIG07 + " mismatch</strong>")
                .append("</td></tr>\n");
        }
        html.append("</tbody>\n</table>\n</section>\n");
    }

    private static void renderFailures(StringBuilder html, ReconciliationReport report) {
        html.append("<section>\n<h2>Failed rows (").append(report.failures.size()).append(")</h2>\n");
        Map<String, Integer> byRule = new LinkedHashMap<String, Integer>();
        for (FailureRow row : report.failures) {
            Integer count = byRule.get(row.rule);
            byRule.put(row.rule, count == null ? 1 : count + 1);
        }
        if (!byRule.isEmpty()) {
            html.append("<p class=\"rules\">");
            for (Map.Entry<String, Integer> entry : byRule.entrySet()) {
                html.append("<span class=\"pill\">").append(esc(entry.getKey())).append(" &times; ")
                    .append(entry.getValue()).append("</span> ");
            }
            html.append("</p>\n");
        }
        html.append("<table>\n<thead><tr><th>table</th><th>source key</th><th>rule</th><th>stage</th>")
            .append("<th>field</th><th>SQLSTATE</th><th>native</th><th>error</th><th>issue</th></tr></thead>\n")
            .append("<tbody>\n");
        for (FailureRow row : report.failures) {
            boolean headline = MIG07.equals(row.issue);
            html.append("<tr").append(headline ? " class=\"mig07\"" : "").append(">")
                .append("<td>").append(esc(row.table)).append("</td>")
                .append("<td><code>").append(esc(row.sourceKey)).append("</code></td>")
                .append("<td>").append(esc(row.rule)).append("</td>")
                .append("<td>").append(esc(row.stage)).append("</td>")
                .append("<td>").append(esc(nvl(row.field, ""))).append("</td>")
                .append("<td>").append(esc(nvl(row.sqlstate, ""))).append("</td>")
                .append("<td>").append(row.nativeError == null ? "" : row.nativeError.toString()).append("</td>")
                .append("<td>").append(esc(nvl(row.error, ""))).append("</td>")
                .append("<td>").append(esc(nvl(row.issue, ""))).append("</td></tr>\n");
        }
        html.append("</tbody>\n</table>\n</section>\n");
    }

    private static void renderSessions(StringBuilder html, ReconciliationReport report) {
        html.append("<section>\n<h2>Devin sessions that produced this code</h2>\n");
        if (report.sessions.isEmpty()) {
            html.append("<p class=\"empty\">No session links recorded.</p>\n</section>\n");
            return;
        }
        html.append("<ul>\n");
        for (SessionLink link : report.sessions) {
            html.append("<li><a href=\"").append(esc(link.url)).append("\" rel=\"noopener\">")
                .append(esc(link.label)).append("</a></li>\n");
        }
        html.append("</ul>\n</section>\n");
    }

    private static String num(long value) {
        return "<td class=\"num\">" + value + "</td>";
    }

    private static String nvl(String value, String fallback) {
        return value == null ? fallback : value;
    }

    static String esc(String text) {
        if (text == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '&': sb.append("&amp;"); break;
                case '<': sb.append("&lt;"); break;
                case '>': sb.append("&gt;"); break;
                case '"': sb.append("&quot;"); break;
                case '\'': sb.append("&#39;"); break;
                default: sb.append(c);
            }
        }
        return sb.toString();
    }

    private static String css() {
        return "body{font-family:system-ui,Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#1f2933}\n"
            + "h1{margin:0 0 4px}h2{margin-top:32px}code{font-family:ui-monospace,Menlo,Consolas,monospace}\n"
            + ".meta{color:#52606d;margin:4px 0}.badge{display:inline-block;padding:6px 12px;border-radius:4px;"
            + "font-weight:600}.badge.ok{background:#e3f9e5;color:#0f5132}"
            + ".badge.fail{background:#fde2e1;color:#7a1d1d}\n"
            + "table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #d9e2ec;padding:6px 8px;"
            + "text-align:left;vertical-align:top}th{background:#f0f4f8}td.num{text-align:right;font-variant-numeric:"
            + "tabular-nums}\ntr.open td{background:#fff4e5}tr.mig07 td{background:#fde2e1;font-weight:600}\n"
            + ".pill{display:inline-block;background:#e4e7eb;border-radius:12px;padding:2px 10px;margin:2px;"
            + "font-size:13px}.note,.empty{color:#52606d}\n";
    }
}

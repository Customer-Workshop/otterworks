package com.otterworks.report.reconciliation;

import com.opencsv.CSVWriter;
import com.otterworks.report.reconciliation.ReconciliationReport.FailureRow;
import com.otterworks.report.reconciliation.ReconciliationReport.TableRow;

import java.io.StringWriter;

/**
 * CSV export per CONTRACTS §10.2: UTF-8, RFC 4180, CRLF, two header-led sections separated by
 * one empty line. Built with OpenCSV like {@code CsvReportGenerator}, but without the report
 * banner rows so the file shape stays exactly as contracted.
 */
public final class ReconciliationCsvWriter {

    static final String[] SUMMARY_HEADER =
        {"section", "table", "extracted", "loaded", "validated", "purged", "failed"};
    static final String[] FAILURE_HEADER =
        {"section", "table", "source_key", "rule", "stage", "field", "sqlstate", "error"};

    private ReconciliationCsvWriter() {
    }

    public static String write(ReconciliationReport report) {
        StringWriter out = new StringWriter();
        CSVWriter csv = new CSVWriter(out, CSVWriter.DEFAULT_SEPARATOR, CSVWriter.DEFAULT_QUOTE_CHARACTER,
                CSVWriter.DEFAULT_QUOTE_CHARACTER, "\r\n");
        csv.writeNext(SUMMARY_HEADER, false);
        for (TableRow row : report.tables) {
            csv.writeNext(new String[] {
                "summary", row.table, Long.toString(row.extracted), Long.toString(row.loaded),
                Long.toString(row.validated), Long.toString(row.purged), Long.toString(row.failed)}, false);
        }
        out.write("\r\n");
        csv.writeNext(FAILURE_HEADER, false);
        for (FailureRow row : report.failures) {
            csv.writeNext(new String[] {
                "failure", row.table, row.sourceKey, row.rule, row.stage, nullToEmpty(row.field),
                nullToEmpty(row.sqlstate), nullToEmpty(row.error)}, false);
        }
        return out.toString();
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}

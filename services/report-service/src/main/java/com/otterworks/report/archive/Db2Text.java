package com.otterworks.report.archive;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.Charset;

/**
 * Rendering helpers shared by both stores so that Db2 and Azure SQL produce byte-identical text.
 *
 * <ul>
 *   <li>TIMESTAMP(12) text: {@code YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN}</li>
 *   <li>DECIMAL: plain text with exactly eight fraction digits</li>
 *   <li>CHAR: trailing spaces removed for display only; raw values are kept alongside</li>
 * </ul>
 */
public final class Db2Text {

    private static final Charset CP037 = Charset.forName("IBM037");
    private static final int TS_FRACTION_DIGITS = 12;
    private static final int DATETIME2_FRACTION_DIGITS = 7;
    private static final int NANOS_TAIL_DIGITS = 5;
    private static final int PG_FRACTION_DIGITS = 6;
    private static final int PG_NANOS_TAIL_DIGITS = 6;

    private Db2Text() {
    }

    /** Right-trims spaces only (Db2 CHAR padding), leaving other whitespace untouched. */
    public static String rtrim(String value) {
        if (value == null) {
            return null;
        }
        int end = value.length();
        while (end > 0 && value.charAt(end - 1) == ' ') {
            end--;
        }
        return value.substring(0, end);
    }

    /** Decodes CCSID 037 (EBCDIC) bytes from a {@code CHAR FOR BIT DATA} column. */
    public static String decodeCp037(byte[] raw) {
        if (raw == null) {
            return null;
        }
        return new String(raw, CP037);
    }

    /** DECIMAL(p,s) to fixed eight fraction digits, {@code -} only when negative. */
    public static String decimal8(BigDecimal value) {
        if (value == null) {
            return null;
        }
        return value.setScale(8, RoundingMode.UNNECESSARY).toPlainString();
    }

    /**
     * Normalises a Db2 TIMESTAMP(12) read as text - either the JDBC form
     * ({@code YYYY-MM-DD HH:MM:SS.NNNNNNNNNNNN}) or Db2's own {@code CHAR()} form
     * ({@code YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN}), fraction possibly shorter - to the
     * twelve-digit Db2 text form used in unload files and JSON.
     */
    public static String timestamp12FromJdbc(String jdbcText) {
        if (jdbcText == null) {
            return null;
        }
        String text = jdbcText.trim();
        String datePart = text.substring(0, 10);
        String timePart = text.substring(11).replace(':', '.');
        int firstDot = timePart.indexOf('.');
        int secondDot = timePart.indexOf('.', firstDot + 1);
        int fractionDot = timePart.indexOf('.', secondDot + 1);
        String hms = fractionDot >= 0 ? timePart.substring(0, fractionDot) : timePart;
        String fraction = fractionDot >= 0 ? timePart.substring(fractionDot + 1) : "";
        return datePart + "-" + hms + "." + padRight(fraction, TS_FRACTION_DIGITS);
    }

    /**
     * Rebuilds the TIMESTAMP(12) text from an Azure SQL {@code DATETIME2(7)} string
     * ({@code YYYY-MM-DD HH:MM:SS.NNNNNNN}) plus the five-digit {@code _NANOS_TAIL}.
     */
    public static String timestamp12FromDateTime2(String dateTime2Text, int nanosTail) {
        if (dateTime2Text == null) {
            return null;
        }
        String text = dateTime2Text.trim().replace('T', ' ');
        String datePart = text.substring(0, 10);
        String timePart = text.substring(11);
        String hms;
        String fraction;
        int dot = timePart.indexOf('.');
        if (dot >= 0) {
            hms = timePart.substring(0, dot);
            fraction = timePart.substring(dot + 1);
        } else {
            hms = timePart;
            fraction = "";
        }
        fraction = padRight(fraction, DATETIME2_FRACTION_DIGITS).substring(0, DATETIME2_FRACTION_DIGITS);
        String tail = String.format("%0" + NANOS_TAIL_DIGITS + "d", nanosTail);
        return datePart + "-" + hms.replace(':', '.') + "." + fraction + tail;
    }

    /**
     * Rebuilds the TIMESTAMP(12) text from a PostgreSQL {@code TIMESTAMP(6)} string
     * ({@code YYYY-MM-DD HH:MM:SS.NNNNNN}, fraction possibly shorter) plus the six-digit
     * {@code _NANOS_TAIL} (fraction digits 7-12).
     */
    public static String timestamp12FromPgTimestamp(String timestampText, int nanosTail) {
        if (timestampText == null) {
            return null;
        }
        String text = timestampText.trim().replace('T', ' ');
        String datePart = text.substring(0, 10);
        String timePart = text.substring(11);
        int dot = timePart.indexOf('.');
        String hms = dot >= 0 ? timePart.substring(0, dot) : timePart;
        String fraction = dot >= 0 ? timePart.substring(dot + 1) : "";
        fraction = padRight(fraction, PG_FRACTION_DIGITS).substring(0, PG_FRACTION_DIGITS);
        String tail = String.format("%0" + PG_NANOS_TAIL_DIGITS + "d", nanosTail);
        return datePart + "-" + hms.replace(':', '.') + "." + fraction + tail;
    }

    /** {@code YYYYMMDD} to ISO {@code YYYY-MM-DD}; other input is returned unchanged. */
    public static String isoDateFromYyyymmdd(String yyyymmdd) {
        if (yyyymmdd == null) {
            return null;
        }
        String text = yyyymmdd.trim();
        if (text.length() != 8 || !text.chars().allMatch(Character::isDigit)) {
            return text;
        }
        return text.substring(0, 4) + "-" + text.substring(4, 6) + "-" + text.substring(6, 8);
    }

    /** ISO {@code YYYY-MM-DD} to {@code YYYYMMDD} (the business-hash rendering of a DATE). */
    public static String yyyymmddFromIso(String iso) {
        if (iso == null) {
            return null;
        }
        return iso.trim().replace("-", "");
    }

    private static String padRight(String value, int length) {
        StringBuilder sb = new StringBuilder(value);
        while (sb.length() < length) {
            sb.append('0');
        }
        return sb.toString();
    }
}

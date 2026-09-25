package com.otterworks.report.util;

import org.junit.jupiter.api.Test;

import java.util.Calendar;
import java.util.Date;
import java.util.TimeZone;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit tests for {@link ReportDateUtils}, which formats and parses dates through
 * Commons Lang {@code DateFormatUtils} and {@code DateUtils}.
 */
public class ReportDateUtilsTest {

    private static Date utc(int year, int month, int day, int hour, int minute, int second) {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.clear();
        cal.set(year, month - 1, day, hour, minute, second);
        return cal.getTime();
    }

    @Test
    public void toIsoStringFormatsInUtc() {
        assertEquals("2024-03-15T08:05:09Z", ReportDateUtils.toIsoString(utc(2024, 3, 15, 8, 5, 9)));
    }

    @Test
    public void toIsoStringReturnsNullForNull() {
        assertNull(ReportDateUtils.toIsoString(null));
    }

    @Test
    public void toDisplayStringFormatsAndHandlesNull() {
        assertEquals("Mar 15, 2024 08:05", ReportDateUtils.toDisplayString(utc(2024, 3, 15, 8, 5, 9)));
        assertEquals("N/A", ReportDateUtils.toDisplayString(null));
    }

    @Test
    public void toFileNameStringFormatsTimestamp() {
        assertEquals("20240315_080509", ReportDateUtils.toFileNameString(utc(2024, 3, 15, 8, 5, 9)));
    }

    @Test
    public void parseIsoDateAcceptsSupportedPatterns() {
        assertEquals(utc(2024, 3, 15, 8, 5, 9), ReportDateUtils.parseIsoDate("2024-03-15T08:05:09Z"));
        assertEquals("2024-03-15T00:00:00Z",
                ReportDateUtils.toIsoString(ReportDateUtils.parseIsoDate("2024-03-15")));
    }

    @Test
    public void parseIsoDateReturnsNullForBlank() {
        assertNull(ReportDateUtils.parseIsoDate(null));
        assertNull(ReportDateUtils.parseIsoDate("   "));
    }

    @Test
    public void parseIsoDateRejectsUnparseableInput() {
        assertThrows(IllegalArgumentException.class, () -> ReportDateUtils.parseIsoDate("not-a-date"));
    }

    @Test
    public void daysAgoSubtractsWholeDays() {
        long delta = System.currentTimeMillis() - ReportDateUtils.daysAgo(7).getTime();
        long sevenDaysMs = 7L * 24 * 60 * 60 * 1000;
        assertTrue(Math.abs(delta - sevenDaysMs) < 60_000, "daysAgo(7) should be about seven days back");
    }

    @Test
    public void startOfTodayAndMonthAreMidnightUtc() {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.setTime(ReportDateUtils.startOfToday());
        assertEquals(0, cal.get(Calendar.HOUR_OF_DAY));
        assertEquals(0, cal.get(Calendar.MINUTE));

        cal.setTime(ReportDateUtils.startOfMonth());
        assertEquals(1, cal.get(Calendar.DAY_OF_MONTH));
        assertEquals(0, cal.get(Calendar.HOUR_OF_DAY));
    }

    @Test
    public void isWithinRangeIsInclusiveAndNullSafe() {
        Date start = utc(2024, 1, 1, 0, 0, 0);
        Date end = utc(2024, 12, 31, 23, 59, 59);
        assertTrue(ReportDateUtils.isWithinRange(utc(2024, 6, 1, 12, 0, 0), start, end));
        assertTrue(ReportDateUtils.isWithinRange(start, start, end));
        assertFalse(ReportDateUtils.isWithinRange(utc(2025, 1, 1, 0, 0, 0), start, end));
        assertFalse(ReportDateUtils.isWithinRange(null, start, end));
    }

    @Test
    public void humanReadableDurationUsesLargestUnit() {
        Date start = utc(2024, 3, 15, 8, 0, 0);
        assertEquals("2h 30m", ReportDateUtils.humanReadableDuration(start, utc(2024, 3, 15, 10, 30, 0)));
        assertEquals("5m 20s", ReportDateUtils.humanReadableDuration(start, utc(2024, 3, 15, 8, 5, 20)));
        assertEquals("45s", ReportDateUtils.humanReadableDuration(start, utc(2024, 3, 15, 8, 0, 45)));
        assertEquals("unknown", ReportDateUtils.humanReadableDuration(null, start));
    }
}

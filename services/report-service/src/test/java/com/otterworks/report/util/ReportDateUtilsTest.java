package com.otterworks.report.util;

import org.junit.jupiter.api.Test;

import java.util.Calendar;
import java.util.Date;
import java.util.TimeZone;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit tests for {@link ReportDateUtils}.
 */
public class ReportDateUtilsTest {

    private static Date utcDate(int year, int month, int day, int hour, int minute, int second) {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.clear();
        cal.set(year, month - 1, day, hour, minute, second);
        return cal.getTime();
    }

    @Test
    public void toIsoStringFormatsUtcDate() {
        Date date = utcDate(2026, 1, 15, 10, 30, 45);
        assertEquals("2026-01-15T10:30:45Z", ReportDateUtils.toIsoString(date));
    }

    @Test
    public void toIsoStringReturnsNullForNullInput() {
        assertNull(ReportDateUtils.toIsoString(null));
    }

    @Test
    public void toDisplayStringFormatsDate() {
        Date date = utcDate(2026, 3, 7, 9, 5, 0);
        assertEquals("Mar 07, 2026 09:05", ReportDateUtils.toDisplayString(date));
    }

    @Test
    public void toDisplayStringReturnsNaForNullInput() {
        assertEquals("N/A", ReportDateUtils.toDisplayString(null));
    }

    @Test
    public void toFileNameStringFormatsDate() {
        Date date = utcDate(2026, 12, 31, 23, 59, 59);
        assertEquals("20261231_235959", ReportDateUtils.toFileNameString(date));
    }

    @Test
    public void toFileNameStringUsesCurrentTimeForNullInput() {
        assertNotNull(ReportDateUtils.toFileNameString(null));
    }

    @Test
    public void parseIsoDateParsesIsoFormat() {
        Date parsed = ReportDateUtils.parseIsoDate("2026-01-15T10:30:45Z");
        assertNotNull(parsed);
        Calendar cal = Calendar.getInstance();
        cal.setTime(parsed);
        assertEquals(2026, cal.get(Calendar.YEAR));
        assertEquals(Calendar.JANUARY, cal.get(Calendar.MONTH));
        assertEquals(15, cal.get(Calendar.DAY_OF_MONTH));
    }

    @Test
    public void parseIsoDateParsesDateOnlyFormat() {
        assertNotNull(ReportDateUtils.parseIsoDate("2026-01-15"));
    }

    @Test
    public void parseIsoDateReturnsNullForBlankInput() {
        assertNull(ReportDateUtils.parseIsoDate(""));
        assertNull(ReportDateUtils.parseIsoDate(null));
    }

    @Test
    public void parseIsoDateThrowsForInvalidInput() {
        assertThrows(IllegalArgumentException.class, () -> ReportDateUtils.parseIsoDate("not-a-date"));
    }

    @Test
    public void startOfTodayHasZeroTimeComponents() {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.setTime(ReportDateUtils.startOfToday());
        assertEquals(0, cal.get(Calendar.HOUR_OF_DAY));
        assertEquals(0, cal.get(Calendar.MINUTE));
        assertEquals(0, cal.get(Calendar.SECOND));
        assertEquals(0, cal.get(Calendar.MILLISECOND));
    }

    @Test
    public void startOfMonthIsFirstDayOfMonth() {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.setTime(ReportDateUtils.startOfMonth());
        assertEquals(1, cal.get(Calendar.DAY_OF_MONTH));
        assertEquals(0, cal.get(Calendar.HOUR_OF_DAY));
    }

    @Test
    public void daysAgoReturnsEarlierDate() {
        Date thirtyDaysAgo = ReportDateUtils.daysAgo(30);
        assertTrue(thirtyDaysAgo.before(new Date()));
        long diffDays = (System.currentTimeMillis() - thirtyDaysAgo.getTime()) / (1000L * 60 * 60 * 24);
        assertEquals(30, diffDays);
    }

    @Test
    public void isWithinRangeReturnsTrueForDateInsideRange() {
        Date start = utcDate(2026, 1, 1, 0, 0, 0);
        Date end = utcDate(2026, 1, 31, 0, 0, 0);
        assertTrue(ReportDateUtils.isWithinRange(utcDate(2026, 1, 15, 0, 0, 0), start, end));
        assertTrue(ReportDateUtils.isWithinRange(start, start, end));
        assertTrue(ReportDateUtils.isWithinRange(end, start, end));
    }

    @Test
    public void isWithinRangeReturnsFalseForDateOutsideRange() {
        Date start = utcDate(2026, 1, 1, 0, 0, 0);
        Date end = utcDate(2026, 1, 31, 0, 0, 0);
        assertFalse(ReportDateUtils.isWithinRange(utcDate(2026, 2, 1, 0, 0, 0), start, end));
        assertFalse(ReportDateUtils.isWithinRange(null, start, end));
        assertFalse(ReportDateUtils.isWithinRange(start, null, end));
        assertFalse(ReportDateUtils.isWithinRange(start, start, null));
    }

    @Test
    public void humanReadableDurationFormatsSeconds() {
        Date start = utcDate(2026, 1, 1, 0, 0, 0);
        Date end = utcDate(2026, 1, 1, 0, 0, 42);
        assertEquals("42s", ReportDateUtils.humanReadableDuration(start, end));
    }

    @Test
    public void humanReadableDurationFormatsMinutes() {
        Date start = utcDate(2026, 1, 1, 0, 0, 0);
        Date end = utcDate(2026, 1, 1, 0, 3, 20);
        assertEquals("3m 20s", ReportDateUtils.humanReadableDuration(start, end));
    }

    @Test
    public void humanReadableDurationFormatsHours() {
        Date start = utcDate(2026, 1, 1, 0, 0, 0);
        Date end = utcDate(2026, 1, 1, 2, 15, 0);
        assertEquals("2h 15m", ReportDateUtils.humanReadableDuration(start, end));
    }

    @Test
    public void humanReadableDurationReturnsUnknownForNulls() {
        assertEquals("unknown", ReportDateUtils.humanReadableDuration(null, new Date()));
        assertEquals("unknown", ReportDateUtils.humanReadableDuration(new Date(), null));
    }
}

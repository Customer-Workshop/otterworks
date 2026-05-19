package com.otterworks.report.util;

import org.junit.Test;

import java.util.Calendar;
import java.util.Date;
import java.util.TimeZone;

import static org.junit.Assert.*;

public class ReportDateUtilsTest {

    @Test
    public void toIsoStringReturnsFormattedDate() {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.set(2025, Calendar.JANUARY, 15, 12, 0, 0);
        cal.set(Calendar.MILLISECOND, 0);
        Date date = cal.getTime();

        String result = ReportDateUtils.toIsoString(date);
        assertNotNull(result);
        assertTrue(result.contains("2025-01-15"));
        assertTrue(result.endsWith("Z"));
    }

    @Test
    public void toIsoStringReturnsNullForNull() {
        assertNull(ReportDateUtils.toIsoString(null));
    }

    @Test
    public void toDisplayStringFormatsDate() {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.set(2025, Calendar.MARCH, 10, 14, 30, 0);
        Date date = cal.getTime();

        String result = ReportDateUtils.toDisplayString(date);
        assertNotNull(result);
        assertTrue(result.contains("Mar"));
        assertTrue(result.contains("10"));
        assertTrue(result.contains("2025"));
    }

    @Test
    public void toDisplayStringReturnsNAForNull() {
        assertEquals("N/A", ReportDateUtils.toDisplayString(null));
    }

    @Test
    public void toFileNameStringFormatsDate() {
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.set(2025, Calendar.JUNE, 5, 8, 30, 0);
        Date date = cal.getTime();

        String result = ReportDateUtils.toFileNameString(date);
        assertNotNull(result);
        assertTrue(result.matches("\\d{8}_\\d{6}"));
    }

    @Test
    public void toFileNameStringUsesCurrentDateForNull() {
        String result = ReportDateUtils.toFileNameString(null);
        assertNotNull(result);
        assertTrue(result.matches("\\d{8}_\\d{6}"));
    }

    @Test
    public void parseIsoDateParsesStandardFormat() {
        Date result = ReportDateUtils.parseIsoDate("2025-01-15T12:00:00Z");
        assertNotNull(result);
    }

    @Test
    public void parseIsoDateParsesDateOnly() {
        Date result = ReportDateUtils.parseIsoDate("2025-01-15");
        assertNotNull(result);
    }

    @Test
    public void parseIsoDateReturnsNullForBlank() {
        assertNull(ReportDateUtils.parseIsoDate(""));
        assertNull(ReportDateUtils.parseIsoDate(null));
    }

    @Test(expected = IllegalArgumentException.class)
    public void parseIsoDateThrowsForInvalidFormat() {
        ReportDateUtils.parseIsoDate("not-a-date");
    }

    @Test
    public void startOfTodayReturnsMidnight() {
        Date today = ReportDateUtils.startOfToday();
        assertNotNull(today);
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.setTime(today);
        assertEquals(0, cal.get(Calendar.HOUR_OF_DAY));
        assertEquals(0, cal.get(Calendar.MINUTE));
        assertEquals(0, cal.get(Calendar.SECOND));
    }

    @Test
    public void startOfMonthReturnsFirstDay() {
        Date start = ReportDateUtils.startOfMonth();
        assertNotNull(start);
        Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        cal.setTime(start);
        assertEquals(1, cal.get(Calendar.DAY_OF_MONTH));
    }

    @Test
    public void daysAgoReturnsPastDate() {
        Date result = ReportDateUtils.daysAgo(7);
        assertNotNull(result);
        assertTrue(result.before(new Date()));
    }

    @Test
    public void isWithinRangeReturnsTrueForDateInRange() {
        Date start = ReportDateUtils.daysAgo(10);
        Date end = new Date();
        Date middle = ReportDateUtils.daysAgo(5);

        assertTrue(ReportDateUtils.isWithinRange(middle, start, end));
    }

    @Test
    public void isWithinRangeReturnsFalseForDateOutOfRange() {
        Date start = ReportDateUtils.daysAgo(5);
        Date end = new Date();
        Date before = ReportDateUtils.daysAgo(10);

        assertFalse(ReportDateUtils.isWithinRange(before, start, end));
    }

    @Test
    public void isWithinRangeReturnsFalseForNullInputs() {
        assertFalse(ReportDateUtils.isWithinRange(null, new Date(), new Date()));
        assertFalse(ReportDateUtils.isWithinRange(new Date(), null, new Date()));
        assertFalse(ReportDateUtils.isWithinRange(new Date(), new Date(), null));
    }

    @Test
    public void humanReadableDurationFormatsHours() {
        Date start = new Date();
        Date end = new Date(start.getTime() + 3661000); // 1h 1m 1s
        String result = ReportDateUtils.humanReadableDuration(start, end);
        assertTrue(result.contains("h"));
    }

    @Test
    public void humanReadableDurationFormatsMinutes() {
        Date start = new Date();
        Date end = new Date(start.getTime() + 125000); // 2m 5s
        String result = ReportDateUtils.humanReadableDuration(start, end);
        assertTrue(result.contains("m"));
    }

    @Test
    public void humanReadableDurationFormatsSeconds() {
        Date start = new Date();
        Date end = new Date(start.getTime() + 45000); // 45s
        String result = ReportDateUtils.humanReadableDuration(start, end);
        assertTrue(result.contains("s"));
    }

    @Test
    public void humanReadableDurationReturnsUnknownForNulls() {
        assertEquals("unknown", ReportDateUtils.humanReadableDuration(null, new Date()));
        assertEquals("unknown", ReportDateUtils.humanReadableDuration(new Date(), null));
    }
}

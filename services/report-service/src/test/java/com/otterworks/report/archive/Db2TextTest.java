package com.otterworks.report.archive;

import org.junit.Test;

import java.math.BigDecimal;
import java.nio.charset.Charset;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

public class Db2TextTest {

    @Test
    public void rtrimStripsOnlyTrailingAsciiSpaces() {
        assertEquals("LOPEZ, M.", Db2Text.rtrim("LOPEZ, M.      "));
        assertEquals("  X", Db2Text.rtrim("  X  "));
        assertEquals("", Db2Text.rtrim("    "));
        assertNull(Db2Text.rtrim(null));
    }

    @Test
    public void decimalAlwaysHasEightFractionDigits() {
        assertEquals("1234.50000000", Db2Text.decimal8(new BigDecimal("1234.5")));
        assertEquals("0.00000000", Db2Text.decimal8(BigDecimal.ZERO));
        assertEquals("-7.12345678", Db2Text.decimal8(new BigDecimal("-7.12345678")));
        assertEquals("12345678901234567890123.12345678",
                Db2Text.decimal8(new BigDecimal("12345678901234567890123.12345678")));
    }

    @Test
    public void jdbcTimestampBecomesDb2Text() {
        assertEquals("2016-03-01-10.15.30.123456789012",
                Db2Text.timestamp12FromJdbc("2016-03-01 10:15:30.123456789012"));
        assertEquals("2016-03-01-10.15.30.123456789012",
                Db2Text.timestamp12FromJdbc("2016-03-01-10.15.30.123456789012"));
        assertEquals("2015-07-02-08.00.00.000000000000", Db2Text.timestamp12FromJdbc("2015-07-02 08:00:00"));
        assertEquals("2015-07-02-08.00.00.100000000000", Db2Text.timestamp12FromJdbc("2015-07-02 08:00:00.1"));
    }

    @Test
    public void dateTime2PlusTailRebuildsTwelveDigits() {
        assertEquals("2016-03-01-10.15.30.123456789012",
                Db2Text.timestamp12FromDateTime2("2016-03-01 10:15:30.1234567", 89012));
        assertEquals("2015-07-02-08.00.00.000000000001",
                Db2Text.timestamp12FromDateTime2("2015-07-02 08:00:00.0000000", 1));
        assertEquals("2015-07-02-08.00.00.000000000000",
                Db2Text.timestamp12FromDateTime2("2015-07-02T08:00:00", 0));
    }

    @Test
    public void cp037BytesDecode() {
        byte[] ebcdic = "LOPEZ, M.  ".getBytes(Charset.forName("IBM037"));
        assertEquals("LOPEZ, M.  ", Db2Text.decodeCp037(ebcdic));
        assertNull(Db2Text.decodeCp037(null));
    }

    @Test
    public void dateConversions() {
        assertEquals("2023-03-01", Db2Text.isoDateFromYyyymmdd("20230301"));
        assertEquals("20230301", Db2Text.yyyymmddFromIso("2023-03-01"));
    }
}

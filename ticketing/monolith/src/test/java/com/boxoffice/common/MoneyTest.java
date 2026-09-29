package com.boxoffice.common;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MoneyTest {

    @Test
    void percentOfRoundsHalfUp() {
        assertEquals(1200, Money.percentOf(10000, 1200));
        assertEquals(1, Money.percentOf(5, 1500));
        assertEquals(0, Money.percentOf(0, 1200));
    }

    @Test
    void formatsCents() {
        assertEquals("$1,234.05", Money.format(123405L));
        assertEquals("$0.99", Money.format(99L));
        assertEquals("-", Money.format((Object) null));
    }
}

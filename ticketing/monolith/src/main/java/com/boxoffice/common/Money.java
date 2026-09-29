package com.boxoffice.common;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class Money {

    private Money() {
    }

    public static long percentOf(long cents, int basisPoints) {
        return BigDecimal.valueOf(cents).multiply(BigDecimal.valueOf(basisPoints))
                .divide(BigDecimal.valueOf(10000), 0, RoundingMode.HALF_UP).longValue();
    }

    public static String format(long cents) {
        return String.format("$%,d.%02d", cents / 100, Math.abs(cents % 100));
    }

    public static String format(Object cents) {
        return cents == null ? "-" : format(((Number) cents).longValue());
    }
}

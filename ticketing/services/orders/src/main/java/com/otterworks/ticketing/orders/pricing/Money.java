package com.otterworks.ticketing.orders.pricing;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Integer-cents arithmetic identical to the monolith's Money helper (HALF_UP). */
public final class Money {

    private Money() {
    }

    public static long percentOf(long cents, int basisPoints) {
        return BigDecimal.valueOf(cents).multiply(BigDecimal.valueOf(basisPoints))
                .divide(BigDecimal.valueOf(10000), 0, RoundingMode.HALF_UP)
                .longValue();
    }
}

package com.otterworks.ticketing.orders.pricing;

/** Demand uplift: +5% per 10% sold (HELD counts as sold), capped at +40%, integer division throughout. */
public final class DemandPricing {

    public static final int MAX_UPLIFT_BP = 4000;

    private DemandPricing() {
    }

    public static int upliftBp(long notAvailable, long total) {
        long safeTotal = Math.max(1, total);
        return (int) Math.min(MAX_UPLIFT_BP, (notAvailable * 100 / safeTotal) / 10 * 500);
    }

    public static long linePrice(long faceValueCents, int demandFactorBp, int upliftBp) {
        return Money.percentOf(faceValueCents, demandFactorBp + upliftBp);
    }
}

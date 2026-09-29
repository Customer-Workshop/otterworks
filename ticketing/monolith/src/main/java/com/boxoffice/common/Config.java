package com.boxoffice.common;

/** Runtime knobs, read from the environment the container was started with. */
public final class Config {

    private Config() {
    }

    public static int intValue(String name, int def) {
        String v = System.getenv(name);
        if (v == null || v.isBlank()) {
            return def;
        }
        return Integer.parseInt(v.trim());
    }

    /** Minutes a seat hold lives before HoldExpiryBean releases it. */
    public static int holdMinutes() {
        return intValue("HOLD_MINUTES", 10);
    }

    /** How long PaymentBean waits on the gateway before failing the order with PAYMENT_TIMEOUT. */
    public static int paymentTimeoutMs() {
        return intValue("PAYMENT_TIMEOUT_MS", 4000);
    }

    /** Simulated gateway latency window. */
    public static int gatewayMinMs() {
        return intValue("GATEWAY_MIN_MS", 40);
    }

    public static int gatewayMaxMs() {
        return intValue("GATEWAY_MAX_MS", 120);
    }

    /** Percentage of gateway calls that decline. */
    public static int gatewayDeclinePct() {
        return intValue("GATEWAY_DECLINE_PCT", 0);
    }

    /** Passes PricingBean makes over the performance seat map when it reprices a hold. */
    public static int pricingPasses() {
        return intValue("PRICING_PASSES", 3);
    }
}

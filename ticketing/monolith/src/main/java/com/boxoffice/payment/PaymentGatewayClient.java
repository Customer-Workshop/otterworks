package com.boxoffice.payment;

import com.boxoffice.common.Config;
import com.boxoffice.common.Refs;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Synchronous card gateway. In this synthetic estate the gateway is simulated in-process:
 * it sleeps for a latency drawn from [GATEWAY_MIN_MS, GATEWAY_MAX_MS], and a call slower
 * than PAYMENT_TIMEOUT_MS is abandoned by the caller.
 */
public class PaymentGatewayClient {

    public enum Outcome { APPROVED, DECLINED, TIMEOUT }

    public record Result(Outcome outcome, String gatewayRef, int latencyMs) {
    }

    public Result authorizeAndCapture(long amountCents, String cardLast4) {
        int min = Config.gatewayMinMs();
        int max = Math.max(min, Config.gatewayMaxMs());
        int latency = min + ThreadLocalRandom.current().nextInt(max - min + 1);
        int timeout = Config.paymentTimeoutMs();
        sleep(Math.min(latency, timeout));
        if (latency > timeout) {
            return new Result(Outcome.TIMEOUT, null, timeout);
        }
        if ("0000".equals(cardLast4) || ThreadLocalRandom.current().nextInt(100) < Config.gatewayDeclinePct()) {
            return new Result(Outcome.DECLINED, Refs.next("GW"), latency);
        }
        return new Result(Outcome.APPROVED, Refs.next("GW"), latency);
    }

    private static void sleep(int ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}

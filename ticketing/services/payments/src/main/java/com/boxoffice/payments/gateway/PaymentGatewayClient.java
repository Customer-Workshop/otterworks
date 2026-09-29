package com.boxoffice.payments.gateway;

import com.boxoffice.payments.config.PaymentsProperties;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.IntBinaryOperator;
import java.util.function.IntConsumer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * The monolith's synchronous card gateway simulator, unchanged: latency drawn uniformly from
 * [GATEWAY_MIN_MS, GATEWAY_MAX_MS]; the caller waits min(latency, PAYMENT_TIMEOUT_MS) and reports TIMEOUT
 * (no gateway reference, latency = timeout) when the draw exceeds the timeout; card 0000 always declines,
 * otherwise a decline happens with probability GATEWAY_DECLINE_PCT.
 */
@Component
public class PaymentGatewayClient {

    public enum Outcome { APPROVED, DECLINED, TIMEOUT }

    public record Result(Outcome outcome, String gatewayRef, int latencyMs) {
    }

    private final PaymentsProperties.Gateway config;
    private final IntBinaryOperator uniform;
    private final IntConsumer sleeper;

    @Autowired
    public PaymentGatewayClient(PaymentsProperties props) {
        this(props.gateway(), (lo, hi) -> lo + ThreadLocalRandom.current().nextInt(hi - lo + 1), PaymentGatewayClient::sleep);
    }

    public PaymentGatewayClient(PaymentsProperties.Gateway config, IntBinaryOperator uniform, IntConsumer sleeper) {
        this.config = config;
        this.uniform = uniform;
        this.sleeper = sleeper;
    }

    public Result authorizeAndCapture(long amountCents, String cardLast4) {
        int min = config.minMs();
        int max = Math.max(min, config.maxMs());
        int latency = uniform.applyAsInt(min, max);
        int timeout = config.timeoutMs();
        sleeper.accept(Math.min(latency, timeout));
        if (latency > timeout) {
            return new Result(Outcome.TIMEOUT, null, timeout);
        }
        if ("0000".equals(cardLast4) || uniform.applyAsInt(0, 99) < config.declinePct()) {
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

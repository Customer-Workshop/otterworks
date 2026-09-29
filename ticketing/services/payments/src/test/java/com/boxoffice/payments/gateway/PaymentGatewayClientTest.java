package com.boxoffice.payments.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import com.boxoffice.payments.config.PaymentsProperties;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Mirrors the monolith's PaymentGatewayClientTest plus the timeout branch, with the random draw pinned. */
class PaymentGatewayClientTest {

    private final List<Integer> slept = new ArrayList<>();

    private PaymentGatewayClient client(int timeout, int latency, int declinePct, int declineDraw) {
        return new PaymentGatewayClient(new PaymentsProperties.Gateway(timeout, 40, 120, declinePct),
                (lo, hi) -> hi == 99 ? declineDraw : latency, slept::add);
    }

    @Test
    void cardEndingInZerosAlwaysDeclines() {
        PaymentGatewayClient.Result r = client(4000, 80, 0, 50).authorizeAndCapture(1000, "0000");
        assertThat(r.outcome()).isEqualTo(PaymentGatewayClient.Outcome.DECLINED);
        assertThat(r.gatewayRef()).startsWith("GW-").hasSize(13);
        assertThat(r.latencyMs()).isEqualTo(80);
    }

    @Test
    void approvesWithGatewayRefUnderDefaultLatency() {
        PaymentGatewayClient.Result r = client(4000, 69, 0, 50).authorizeAndCapture(42836, "4242");
        assertThat(r.outcome()).isEqualTo(PaymentGatewayClient.Outcome.APPROVED);
        assertThat(r.gatewayRef()).startsWith("GW-");
        assertThat(r.latencyMs()).isEqualTo(69);
        assertThat(slept).containsExactly(69);
    }

    @Test
    void latencyAboveTimeoutIsTimeoutWithoutGatewayRef() {
        PaymentGatewayClient.Result r = client(1, 40, 0, 50).authorizeAndCapture(42836, "4242");
        assertThat(r.outcome()).isEqualTo(PaymentGatewayClient.Outcome.TIMEOUT);
        assertThat(r.gatewayRef()).isNull();
        assertThat(r.latencyMs()).isEqualTo(1);
        assertThat(slept).as("caller waits only up to the timeout").containsExactly(1);
    }

    @Test
    void declinePercentageDrivesRandomDeclines() {
        assertThat(client(4000, 50, 30, 29).authorizeAndCapture(1000, "4242").outcome())
                .isEqualTo(PaymentGatewayClient.Outcome.DECLINED);
        assertThat(client(4000, 50, 30, 30).authorizeAndCapture(1000, "4242").outcome())
                .isEqualTo(PaymentGatewayClient.Outcome.APPROVED);
    }

    @Test
    void realClientHonoursConfiguredLatencyWindow() {
        PaymentsProperties props = new PaymentsProperties("tkt01", null, null, new PaymentsProperties.Gateway(4000, 5, 10, 0), null);
        PaymentGatewayClient.Result r = new PaymentGatewayClient(props).authorizeAndCapture(100, "4242");
        assertThat(r.outcome()).isEqualTo(PaymentGatewayClient.Outcome.APPROVED);
        assertThat(r.latencyMs()).isBetween(5, 10);
    }
}

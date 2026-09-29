package com.boxoffice.payment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class PaymentGatewayClientTest {

    private final PaymentGatewayClient gateway = new PaymentGatewayClient();

    @Test
    void cardEndingInZerosIsAlwaysDeclined() {
        assertEquals(PaymentGatewayClient.Outcome.DECLINED, gateway.authorizeAndCapture(1000, "0000").outcome());
    }

    @Test
    void defaultLatencyIsWithinTimeoutAndApproves() {
        PaymentGatewayClient.Result r = gateway.authorizeAndCapture(1000, "4242");
        assertEquals(PaymentGatewayClient.Outcome.APPROVED, r.outcome());
        assertNotNull(r.gatewayRef());
    }
}

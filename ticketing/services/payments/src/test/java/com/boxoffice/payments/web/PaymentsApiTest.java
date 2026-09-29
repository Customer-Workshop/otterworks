package com.boxoffice.payments.web;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.boxoffice.payments.SpringTestBase;
import com.boxoffice.payments.domain.PaymentStatus;
import com.boxoffice.payments.repo.PaymentRepository;
import com.boxoffice.payments.service.PaymentMetrics;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;

class PaymentsApiTest extends SpringTestBase {

    @Autowired MockMvc mvc;
    @Autowired PaymentRepository repo;
    @Autowired PaymentMetrics metrics;

    @BeforeEach
    void seedOnePayment() {
        if (repo.findByOrderRef("BO-API0000001").isEmpty()) {
            Instant at = Instant.parse("2026-09-29T00:00:00Z");
            repo.insertAttempt("BO-API0000001", 1, "TIMEOUT", 4000, at);
            repo.insertAttempt("BO-API0000001", 2, "APPROVED", 55, at.plusSeconds(5));
            repo.insertPayment("BO-API0000001", "HLD-API1", 42836, "USD", PaymentStatus.CAPTURED, "GW-APITEST0001", "4242", at.plusSeconds(5));
        }
    }

    @Test
    void paymentByOrderRefHasTheContractShape() throws Exception {
        mvc.perform(get("/api/payments/BO-API0000001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderRef").value("BO-API0000001"))
                .andExpect(jsonPath("$.status").value("CAPTURED"))
                .andExpect(jsonPath("$.amountCents").value(42836))
                .andExpect(jsonPath("$.gatewayRef").value("GW-APITEST0001"))
                .andExpect(jsonPath("$.cardLast4").value("4242"))
                .andExpect(jsonPath("$.attempts.length()").value(2))
                .andExpect(jsonPath("$.attempts[0].attemptNo").value(1))
                .andExpect(jsonPath("$.attempts[0].outcome").value("TIMEOUT"))
                .andExpect(jsonPath("$.attempts[0].latencyMs").value(4000))
                .andExpect(jsonPath("$.attempts[1].outcome").value("APPROVED"));
    }

    @Test
    void unknownOrderRefIs404() throws Exception {
        mvc.perform(get("/api/payments/BO-NOPE")).andExpect(status().isNotFound());
    }

    @Test
    void statsExposeTheReconciliationCounters() throws Exception {
        mvc.perform(get("/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paymentsCaptured").isNumber())
                .andExpect(jsonPath("$.capturedCents").isNumber())
                .andExpect(jsonPath("$.paymentsDeclined").isNumber())
                .andExpect(jsonPath("$.paymentsTimeout").isNumber())
                .andExpect(jsonPath("$.paymentsExpired").isNumber())
                .andExpect(jsonPath("$.attempts").isNumber())
                .andExpect(jsonPath("$.duplicatesSuppressed").isNumber());
    }

    @Test
    void actuatorHealthAndPrometheusAreExposed() throws Exception {
        metrics.gatewayLatency("APPROVED", 69);
        metrics.duplicateSuppressed();
        mvc.perform(get("/actuator/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("UP"));
        mvc.perform(get("/actuator/health/readiness")).andExpect(status().isOk());
        mvc.perform(get("/actuator/health/liveness")).andExpect(status().isOk());
        mvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("payments_gateway_latency_seconds_bucket")))
                .andExpect(content().string(containsString("payments_duplicates_suppressed_total")));
    }
}

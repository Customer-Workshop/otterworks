package com.boxoffice.payments.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.boxoffice.payments.SpringTestBase;
import com.boxoffice.payments.config.PaymentsProperties;
import com.boxoffice.payments.domain.PaymentStats;
import com.boxoffice.payments.events.Fixtures;
import com.boxoffice.payments.events.OrderPlaced;
import com.boxoffice.payments.gateway.PaymentGatewayClient;
import com.boxoffice.payments.repo.PaymentRepository;
import com.boxoffice.payments.service.OutcomeEvent;
import com.boxoffice.payments.service.OutcomeOutbox;
import com.boxoffice.payments.service.PaymentMetrics;
import com.boxoffice.payments.service.PaymentProcessor;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Contract tests: the recorded monolith outcomes in src/test/resources/contracts/*.json (fresh seed, performance 1,
 * two seats, POST /api/purchase) must be reproduced by this service from the equivalent order-placed record.
 * The gateway's random draw is pinned to the latency the monolith happened to record so attempts compare exactly.
 */
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MonolithContractTest extends SpringTestBase {

    private static final Instant NOW = Instant.parse("2026-09-29T00:00:10Z");
    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    @Autowired PaymentRepository repo;
    @Autowired PaymentMetrics metrics;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;
    @Autowired OutcomeOutbox outbox;

    private final AtomicInteger gatewayCalls = new AtomicInteger();

    @BeforeAll
    void cleanSlate() {
        jdbc.update("DELETE FROM payment_attempts");
        jdbc.update("DELETE FROM payments");
    }

    private PaymentProcessor processor(int timeoutMs, int latency) {
        PaymentGatewayClient gateway = new PaymentGatewayClient(new PaymentsProperties.Gateway(timeoutMs, 40, 120, 0),
                (lo, hi) -> { if (hi != 99) gatewayCalls.incrementAndGet(); return hi == 99 ? 99 : latency; }, ms -> { });
        return new PaymentProcessor(repo, gateway, metrics, CLOCK, tx, outbox);
    }

    private static OrderPlaced orderFor(JsonNode fx, String orderRef) {
        String card = fx.has("request") ? fx.get("request").get("cardLast4").asText() : "4242";
        return Fixtures.orderPlaced(orderRef, card, NOW.plusSeconds(600));
    }

    @Test
    @Order(1)
    void approvedPurchaseIsCapturedLikeTheMonolith() {
        JsonNode fx = Fixtures.contract("approved");
        JsonNode payment = fx.get("payments").get(0);
        JsonNode attempt = fx.get("paymentAttempts").get(0);
        OrderPlaced placed = orderFor(fx, "BO-APPROVED01");
        assertThat(placed.totalCents()).isEqualTo(fx.get("order").get("totalCents").asLong());

        OutcomeEvent out = processor(4000, attempt.get("latency_ms").asInt()).process(placed);

        assertThat(fx.get("purchaseResponse").get("paymentOutcome").asText()).isEqualTo("APPROVED");
        assertThat(out.captured()).isNotNull();
        assertThat(out.failed()).isNull();
        assertThat(out.captured().amountCents()).isEqualTo(payment.get("amount_cents").asLong());
        assertThat(out.captured().currency()).isEqualTo(payment.get("currency").asText());
        assertThat(out.captured().cardLast4()).isEqualTo(payment.get("card_last4").asText());
        assertThat(out.captured().gatewayRef() != null).isEqualTo(payment.get("has_gateway_ref").asBoolean());
        assertThat(out.captured().attemptNo()).isEqualTo(attempt.get("attempt_no").asInt());
        assertThat(out.captured().latencyMs()).isEqualTo(attempt.get("latency_ms").asInt());
        assertThat(out.captured().capturedAt()).isEqualTo(NOW);
        assertThat(out.captured().order().holdRef()).isEqualTo(placed.holdRef());
        assertThat(out.captured().order().items()).hasSize(fx.get("purchaseResponse").get("tickets").asInt());

        var stored = repo.findByOrderRef("BO-APPROVED01").orElseThrow();
        assertThat(stored.status().name()).isEqualTo(payment.get("status").asText());
        assertThat(repo.attemptsFor("BO-APPROVED01")).singleElement().satisfies(a -> {
            assertThat(a.attemptNo()).isEqualTo(1);
            assertThat(a.outcome()).isEqualTo(attempt.get("outcome").asText());
            assertThat(a.latencyMs()).isEqualTo(attempt.get("latency_ms").asInt());
        });
    }

    @Test
    @Order(2)
    void declinedCardFailsTheOrderLikeTheMonolith() {
        JsonNode fx = Fixtures.contract("declined");
        JsonNode payment = fx.get("payments").get(0);
        JsonNode attempt = fx.get("paymentAttempts").get(0);
        OrderPlaced placed = orderFor(fx, "BO-DECLINED01");
        assertThat(placed.cardLast4()).isEqualTo("0000");

        OutcomeEvent out = processor(4000, attempt.get("latency_ms").asInt()).process(placed);

        assertThat(out.captured()).isNull();
        assertThat(out.failed().outcome()).isEqualTo(fx.get("purchaseResponse").get("paymentOutcome").asText());
        assertThat(out.failed().orderStatus()).isEqualTo(fx.get("order").get("status").asText());
        assertThat(out.failed().amountCents()).isEqualTo(payment.get("amount_cents").asLong());
        assertThat(out.failed().gatewayRef() != null).isEqualTo(payment.get("has_gateway_ref").asBoolean());
        assertThat(out.failed().attemptNo()).isEqualTo(attempt.get("attempt_no").asInt());
        assertThat(out.failed().latencyMs()).isEqualTo(attempt.get("latency_ms").asInt());
        assertThat(out.failed().holdRef()).as("hold %s is released by seats", fx.get("hold").get("hold_status").asText())
                .isEqualTo(placed.holdRef());
        assertThat(repo.findByOrderRef("BO-DECLINED01").orElseThrow().status().name()).isEqualTo(payment.get("status").asText());
        assertThat(repo.attemptsFor("BO-DECLINED01")).singleElement()
                .satisfies(a -> assertThat(a.outcome()).isEqualTo(attempt.get("outcome").asText()));
    }

    @Test
    @Order(3)
    void gatewayTimeoutTimesOutTheOrderLikeTheMonolith() {
        JsonNode fx = Fixtures.contract("timeout");
        JsonNode payment = fx.get("payments").get(0);
        JsonNode attempt = fx.get("paymentAttempts").get(0);
        int timeoutMs = fx.get("monolithEnv").get("PAYMENT_TIMEOUT_MS").asInt();
        OrderPlaced placed = orderFor(fx, "BO-TIMEOUT001");

        OutcomeEvent out = processor(timeoutMs, 40).process(placed);

        assertThat(out.failed().outcome()).isEqualTo(fx.get("purchaseResponse").get("paymentOutcome").asText());
        assertThat(out.failed().orderStatus()).isEqualTo(fx.get("order").get("status").asText());
        assertThat(out.failed().gatewayRef()).as("has_gateway_ref=%s", payment.get("has_gateway_ref")).isNull();
        assertThat(out.failed().latencyMs()).isEqualTo(attempt.get("latency_ms").asInt()).isEqualTo(timeoutMs);
        assertThat(out.failed().attemptNo()).isEqualTo(attempt.get("attempt_no").asInt());
        var stored = repo.findByOrderRef("BO-TIMEOUT001").orElseThrow();
        assertThat(stored.status().name()).isEqualTo(payment.get("status").asText());
        assertThat(stored.gatewayRef()).isNull();
        assertThat(repo.attemptsFor("BO-TIMEOUT001")).singleElement()
                .satisfies(a -> assertThat(a.outcome()).isEqualTo(attempt.get("outcome").asText()));
    }

    @Test
    @Order(4)
    void lapsedHoldIsCancelledWithoutChargingLikeTheMonolithSweep() {
        JsonNode fx = Fixtures.contract("hold_expired");
        OrderPlaced placed = Fixtures.orderPlaced("BO-EXPIRED001", "4242", NOW.minusSeconds(60));
        int callsBefore = gatewayCalls.get();

        OutcomeEvent out = processor(4000, 69).process(placed);

        assertThat(gatewayCalls.get()).as("no gateway call for a lapsed hold").isEqualTo(callsBefore);
        assertThat(out.failed().outcome()).isEqualTo("HOLD_EXPIRED");
        assertThat(out.failed().orderStatus()).isEqualTo(fx.get("order").get("status").asText());
        assertThat(out.failed().amountCents()).isEqualTo(fx.get("order").get("totalCents").asLong());
        assertThat(out.failed().gatewayRef()).isNull();
        assertThat(out.failed().attemptNo()).isZero();
        assertThat(repo.attemptsFor("BO-EXPIRED001")).as("monolith recorded %s attempts", fx.get("paymentAttempts"))
                .hasSize(fx.get("paymentAttempts").size());
        assertThat(repo.findByOrderRef("BO-EXPIRED001").orElseThrow().status().name())
                .as("monolith has %s payments rows; the service keeps one EXPIRED marker as its idempotency key",
                        fx.get("payments").size())
                .isEqualTo("EXPIRED");
        assertThat(fx.get("hold").get("seats_still_held").asInt()).isZero();
    }

    @Test
    @Order(5)
    void redeliveredOrderPlacedIsSuppressedAndRedrivesTheStoredOutcome() {
        JsonNode fx = Fixtures.contract("approved");
        OrderPlaced placed = orderFor(fx, "BO-APPROVED01");
        int callsBefore = gatewayCalls.get();
        var before = repo.findByOrderRef("BO-APPROVED01").orElseThrow();

        OutcomeEvent out = processor(4000, 69).process(placed);

        assertThat(gatewayCalls.get()).isEqualTo(callsBefore);
        assertThat(out.duplicate()).isTrue();
        assertThat(out.captured()).isNotNull();
        assertThat(out.captured().gatewayRef()).isEqualTo(before.gatewayRef());
        assertThat(out.captured().attemptNo()).isEqualTo(1);
        assertThat(repo.attemptsFor("BO-APPROVED01")).hasSize(1);
        assertThat(repo.stats().duplicatesSuppressed()).isEqualTo(1);
    }

    @Test
    @Order(6)
    void statsMatchTheMonolithCountersAfterTheSameFourPurchases() {
        JsonNode monolith = Fixtures.contract("stats").get("stats");
        PaymentStats stats = repo.stats();

        assertThat(stats.paymentsCaptured()).isEqualTo(monolith.get("paymentsCaptured").asLong());
        assertThat(stats.capturedCents()).isEqualTo(monolith.get("capturedCents").asLong());
        JsonNode byStatus = monolith.get("ordersByStatus");
        assertThat(stats.paymentsCaptured()).isEqualTo(byStatus.get("CONFIRMED").asLong());
        assertThat(stats.paymentsDeclined()).isEqualTo(byStatus.get("PAYMENT_FAILED").asLong());
        assertThat(stats.paymentsTimeout()).isEqualTo(byStatus.get("PAYMENT_TIMEOUT").asLong());
        assertThat(stats.paymentsExpired()).isEqualTo(byStatus.get("CANCELLED").asLong());
        assertThat(stats.attempts()).isEqualTo(3);
        assertThat(stats.duplicatesSuppressed()).isEqualTo(1);
    }
}

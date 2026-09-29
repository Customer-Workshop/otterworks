package com.boxoffice.payments.service;

import com.boxoffice.payments.domain.Payment;
import com.boxoffice.payments.domain.PaymentAttempt;
import com.boxoffice.payments.domain.PaymentStatus;
import com.boxoffice.payments.events.OrderPlaced;
import com.boxoffice.payments.events.PaymentCaptured;
import com.boxoffice.payments.events.PaymentFailed;
import com.boxoffice.payments.gateway.PaymentGatewayClient;
import com.boxoffice.payments.repo.PaymentRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * The monolith's PaymentBean.charge, driven by an order-placed record instead of an order id.
 *
 * <ol>
 *   <li>a payment already exists for orderRef → duplicate delivery: no gateway call, no new rows, the stored
 *       outcome is rebuilt so the caller can re-drive the downstream event, duplicates_suppressed++;</li>
 *   <li>holdExpiresAt is in the past → HOLD_EXPIRED: no gateway call (HoldExpiryBean semantics), payment
 *       EXPIRED, order CANCELLED;</li>
 *   <li>otherwise the gateway is charged and payment_attempts + payments are written in one transaction.</li>
 * </ol>
 * The gateway call is deliberately outside the transaction (it sleeps up to PAYMENT_TIMEOUT_MS).
 */
@Service
public class PaymentProcessor {

    private static final Logger log = LoggerFactory.getLogger(PaymentProcessor.class);

    private final PaymentRepository repo;
    private final PaymentGatewayClient gateway;
    private final PaymentMetrics metrics;
    private final Clock clock;
    private final TransactionTemplate tx;

    public PaymentProcessor(PaymentRepository repo, PaymentGatewayClient gateway, PaymentMetrics metrics, Clock clock,
                            TransactionTemplate tx) {
        this.repo = repo;
        this.gateway = gateway;
        this.metrics = metrics;
        this.clock = clock;
        this.tx = tx;
    }

    public OutcomeEvent process(OrderPlaced placed) {
        Optional<Payment> existing = repo.findByOrderRef(placed.orderRef());
        if (existing.isPresent()) {
            return suppressDuplicate(placed, existing.get());
        }
        Instant now = clock.instant();
        if (placed.holdExpiresAt() != null && placed.holdExpiresAt().isBefore(now)) {
            return record(placed, PaymentStatus.EXPIRED, null, 0, now, false);
        }
        PaymentGatewayClient.Result r = gateway.authorizeAndCapture(placed.totalCents(), placed.cardLast4());
        metrics.gatewayLatency(r.outcome().name(), r.latencyMs());
        PaymentStatus status = switch (r.outcome()) {
            case APPROVED -> PaymentStatus.CAPTURED;
            case DECLINED -> PaymentStatus.DECLINED;
            case TIMEOUT -> PaymentStatus.TIMEOUT;
        };
        return record(placed, status, r.gatewayRef(), r.latencyMs(), clock.instant(), true);
    }

    private OutcomeEvent record(OrderPlaced placed, PaymentStatus status, String gatewayRef, int latencyMs,
                                Instant at, boolean gatewayCalled) {
        int attemptNo;
        try {
            attemptNo = tx.execute(txStatus -> {
                int no = repo.nextAttemptNo(placed.orderRef());
                if (gatewayCalled) {
                    repo.insertAttempt(placed.orderRef(), no, status.attemptOutcome(), latencyMs, at);
                }
                repo.insertPayment(placed.orderRef(), placed.holdRef(), placed.totalCents(), placed.currencyOrDefault(),
                        status, gatewayRef, placed.cardLast4(), at);
                return no;
            });
        } catch (DuplicateKeyException race) {
            // two partitions/replicas raced on the same orderRef; the first writer wins and this delivery is a duplicate
            throw new ConcurrentDeliveryException(placed.orderRef(), race);
        }
        metrics.outcome(status.name());
        log.info("payment {} {} amount={} attempt={} latency={}ms", placed.orderRef(), status, placed.totalCents(), attemptNo, latencyMs);
        return toEvent(placed, status, gatewayRef, gatewayCalled ? attemptNo : 0, latencyMs, at, false);
    }

    private OutcomeEvent suppressDuplicate(OrderPlaced placed, Payment payment) {
        repo.incrementDuplicateDeliveries(payment.orderRef());
        metrics.duplicateSuppressed();
        List<PaymentAttempt> attempts = repo.attemptsFor(payment.orderRef());
        PaymentAttempt last = attempts.isEmpty() ? null : attempts.get(attempts.size() - 1);
        log.info("duplicate order-placed for {} suppressed (stored outcome {})", payment.orderRef(), payment.status());
        return toEvent(placed, payment.status(), payment.gatewayRef(), last == null ? 0 : last.attemptNo(),
                last == null ? 0 : last.latencyMs(), payment.createdAt(), true);
    }

    private static OutcomeEvent toEvent(OrderPlaced placed, PaymentStatus status, String gatewayRef, int attemptNo,
                                        int latencyMs, Instant at, boolean duplicate) {
        if (status.captured()) {
            return OutcomeEvent.of(PaymentCaptured.from(placed, gatewayRef, attemptNo, latencyMs, at), duplicate);
        }
        return OutcomeEvent.of(new PaymentFailed(placed.orderRef(), placed.holdRef(), status.failureOutcome(),
                status.orderStatus(), placed.totalCents(), placed.cardLast4(), attemptNo, latencyMs, gatewayRef, at), duplicate);
    }

    public static class ConcurrentDeliveryException extends RuntimeException {
        public ConcurrentDeliveryException(String orderRef, Throwable cause) {
            super("payment for " + orderRef + " was recorded concurrently", cause);
        }
    }
}

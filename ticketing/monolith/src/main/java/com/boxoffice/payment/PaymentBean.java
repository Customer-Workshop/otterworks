package com.boxoffice.payment;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import com.boxoffice.inventory.SeatHoldBean;
import jakarta.ejb.EJB;
import jakarta.ejb.Stateless;
import java.util.Map;

/**
 * Charges an order through the gateway inside the purchase transaction.
 * On decline or timeout it fails the order and releases the hold itself.
 */
@Stateless
public class PaymentBean {

    @EJB
    private SeatHoldBean holds;

    private final PaymentGatewayClient gateway = new PaymentGatewayClient();

    public PaymentGatewayClient.Outcome charge(long orderId, String cardLast4) {
        Map<String, Object> order = Db.one("SELECT total_cents, hold_id, order_ref FROM orders WHERE id = ?", orderId);
        long amount = ((Number) order.get("total_cents")).longValue();
        long attempt = Db.scalarLong("SELECT COUNT(*) FROM payment_attempts WHERE order_id = ?", orderId) + 1;

        PaymentGatewayClient.Result r = gateway.authorizeAndCapture(amount, cardLast4);
        Db.update("INSERT INTO payment_attempts (order_id, attempt_no, outcome, latency_ms) VALUES (?, ?, ?, ?)",
                orderId, (int) attempt, r.outcome().name(), r.latencyMs());

        switch (r.outcome()) {
            case APPROVED -> Db.update("""
                    INSERT INTO payments (order_id, amount_cents, status, gateway_ref, card_last4)
                    VALUES (?, ?, 'CAPTURED', ?, ?)""", orderId, amount, r.gatewayRef(), cardLast4);
            case DECLINED -> {
                Db.update("""
                        INSERT INTO payments (order_id, amount_cents, status, gateway_ref, card_last4)
                        VALUES (?, ?, 'DECLINED', ?, ?)""", orderId, amount, r.gatewayRef(), cardLast4);
                Db.update("UPDATE orders SET status = 'PAYMENT_FAILED', updated_at = now() WHERE id = ?", orderId);
                holds.release(((Number) order.get("hold_id")).longValue(), "RELEASED");
            }
            case TIMEOUT -> {
                Db.update("""
                        INSERT INTO payments (order_id, amount_cents, status, card_last4)
                        VALUES (?, ?, 'TIMEOUT', ?)""", orderId, amount, cardLast4);
                Db.update("UPDATE orders SET status = 'PAYMENT_TIMEOUT', updated_at = now() WHERE id = ?", orderId);
                holds.release(((Number) order.get("hold_id")).longValue(), "RELEASED");
            }
            default -> throw new IllegalStateException();
        }
        AuditLog.record("payment", "PAYMENT_" + r.outcome().name(), (String) order.get("order_ref"),
                "amount=" + amount + " latency=" + r.latencyMs());
        return r.outcome();
    }

    public void refund(long paymentId, long amountCents, String reason) {
        Db.update("INSERT INTO refunds (payment_id, amount_cents, reason) VALUES (?, ?, ?)", paymentId, amountCents, reason);
        Db.update("UPDATE payments SET status = 'REFUNDED' WHERE id = ?", paymentId);
        Db.update("UPDATE orders SET status = 'REFUNDED', updated_at = now() WHERE id = (SELECT order_id FROM payments WHERE id = ?)",
                paymentId);
        AuditLog.record("payment", "REFUNDED", "pay:" + paymentId, reason);
    }
}

package com.otterworks.ticketing.orders.order;

import com.otterworks.ticketing.orders.pricing.Quote;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private static final String ORDER_SELECT = """
            SELECT o.id, o.order_ref, o.client_ref, o.customer_email, o.performance_id, o.hold_ref, o.hold_expires_at,
                   o.status, o.payment_outcome, o.subtotal_cents, o.fees_cents, o.total_cents, o.channel, o.card_last4,
                   o.created_at, o.updated_at, e.title AS event_title, p.starts_at, v.name AS venue_name
            FROM orders o
            JOIN performances p ON p.id = o.performance_id
            JOIN events e ON e.id = p.event_id
            JOIN venues v ON v.id = p.venue_id
            """;

    private final JdbcClient jdbc;

    public OrderRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderRecord> byRef(String orderRef) {
        return jdbc.sql(ORDER_SELECT + "WHERE o.order_ref = :ref").param("ref", orderRef)
                .query(OrderRepository::mapOrder).optional();
    }

    public Optional<OrderRecord> byClientRef(String clientRef) {
        return jdbc.sql(ORDER_SELECT + "WHERE o.client_ref = :ref").param("ref", clientRef)
                .query(OrderRepository::mapOrder).optional();
    }

    public List<OrderItemRecord> items(long orderId) {
        return jdbc.sql("""
                        SELECT seat_inventory_id, price_zone_id, price_cents, section, row_label, seat_number,
                               zone_code, zone_name, ticket_code
                        FROM order_items WHERE order_id = :id ORDER BY section, row_label, seat_number""")
                .param("id", orderId)
                .query((rs, i) -> new OrderItemRecord(rs.getLong(1), rs.getLong(2), rs.getLong(3), rs.getString(4),
                        rs.getString(5), rs.getInt(6), rs.getString(7), rs.getString(8), rs.getString(9)))
                .list();
    }

    public List<Quote.Fee> fees(long orderId) {
        return jdbc.sql("SELECT fee_type, amount_cents FROM order_fees WHERE order_id = :id ORDER BY id")
                .param("id", orderId)
                .query((rs, i) -> new Quote.Fee(rs.getString(1), rs.getLong(2)))
                .list();
    }

    public long insertOrder(String orderRef, PlaceOrderRequest req, String holdRef, OffsetDateTime holdExpiresAt,
                            Quote quote, OffsetDateTime createdAt) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.sql("""
                        INSERT INTO orders (order_ref, client_ref, customer_email, performance_id, hold_ref, hold_expires_at,
                                            delivery_method_id, promo_code_id, status, payment_outcome,
                                            subtotal_cents, fees_cents, total_cents, channel, card_last4, created_at, updated_at)
                        VALUES (:orderRef, :clientRef, :email, :performanceId, :holdRef, :holdExpiresAt,
                                :deliveryId, :promoId, 'PENDING_PAYMENT', 'PENDING',
                                :subtotal, :fees, :total, :channel, :card, :createdAt, :createdAt)""")
                .param("orderRef", orderRef)
                .param("clientRef", req.clientRefOrNull())
                .param("email", req.normalisedEmail())
                .param("performanceId", quote.performanceId())
                .param("holdRef", holdRef)
                .param("holdExpiresAt", holdExpiresAt)
                .param("deliveryId", quote.deliveryMethodId())
                .param("promoId", quote.promoCodeId())
                .param("subtotal", quote.subtotalCents())
                .param("fees", quote.feesCents())
                .param("total", quote.totalCents())
                .param("channel", req.channel())
                .param("card", req.cardLast4OrDefault())
                .param("createdAt", createdAt)
                .update(keys, "id");
        return keys.getKey().longValue();
    }

    public void insertItems(long orderId, List<Quote.Line> lines) {
        for (Quote.Line line : lines) {
            jdbc.sql("""
                            INSERT INTO order_items (order_id, seat_inventory_id, price_zone_id, price_cents, section, row_label,
                                                     seat_number, zone_code, zone_name)
                            VALUES (:orderId, :si, :pz, :price, :section, :row, :seat, :zoneCode, :zoneName)""")
                    .param("orderId", orderId)
                    .param("si", line.seatInventoryId())
                    .param("pz", line.priceZoneId())
                    .param("price", line.priceCents())
                    .param("section", line.section() == null ? "" : line.section())
                    .param("row", line.rowLabel() == null ? "" : line.rowLabel())
                    .param("seat", line.seatNumber())
                    .param("zoneCode", line.zoneCode() == null ? "" : line.zoneCode())
                    .param("zoneName", line.zoneName() == null ? "" : line.zoneName())
                    .update();
        }
    }

    public void insertFees(long orderId, List<Quote.Fee> fees) {
        for (Quote.Fee fee : fees) {
            jdbc.sql("INSERT INTO order_fees (order_id, fee_type, amount_cents) VALUES (:orderId, :type, :amount)")
                    .param("orderId", orderId).param("type", fee.feeType()).param("amount", fee.amountCents())
                    .update();
        }
    }

    public void incrementPromoUse(long promoCodeId) {
        jdbc.sql("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = :id").param("id", promoCodeId).update();
    }

    /** Transition a PENDING_PAYMENT order by ref; returns rows updated (0 = unknown or already terminal). */
    public int transitionByRef(String orderRef, OrderStatus to, String paymentOutcome) {
        return jdbc.sql("""
                        UPDATE orders SET status = :status, payment_outcome = :outcome, updated_at = now()
                        WHERE order_ref = :ref AND status = 'PENDING_PAYMENT'""")
                .param("status", to.name()).param("outcome", paymentOutcome).param("ref", orderRef).update();
    }

    /** Cancel every PENDING_PAYMENT order attached to a hold; returns rows updated. */
    public int cancelPendingByHold(String holdRef) {
        return jdbc.sql("""
                        UPDATE orders SET status = 'CANCELLED', payment_outcome = 'HOLD_EXPIRED', updated_at = now()
                        WHERE hold_ref = :ref AND status = 'PENDING_PAYMENT'""")
                .param("ref", holdRef).update();
    }

    public int stampTicket(long orderId, long seatInventoryId, String ticketCode) {
        return jdbc.sql("""
                        UPDATE order_items SET ticket_code = :code
                        WHERE order_id = :orderId AND seat_inventory_id = :si AND ticket_code IS DISTINCT FROM :code""")
                .param("code", ticketCode).param("orderId", orderId).param("si", seatInventoryId).update();
    }

    private static OrderRecord mapOrder(ResultSet rs, int i) throws SQLException {
        return new OrderRecord(
                rs.getLong("id"), rs.getString("order_ref"), rs.getString("client_ref"), rs.getString("customer_email"),
                rs.getLong("performance_id"), rs.getString("hold_ref"), rs.getObject("hold_expires_at", OffsetDateTime.class),
                rs.getString("status"), rs.getString("payment_outcome"), rs.getLong("subtotal_cents"),
                rs.getLong("fees_cents"), rs.getLong("total_cents"), rs.getString("channel"), rs.getString("card_last4"),
                rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class),
                rs.getString("event_title"), utc(rs.getTimestamp("starts_at")), rs.getString("venue_name"));
    }

    /** Reference timestamps are seeded as UTC TIMESTAMP (no zone), exactly like the monolith. */
    static OffsetDateTime utc(java.sql.Timestamp ts) {
        return ts == null ? null : ts.toLocalDateTime().atOffset(ZoneOffset.UTC);
    }
}

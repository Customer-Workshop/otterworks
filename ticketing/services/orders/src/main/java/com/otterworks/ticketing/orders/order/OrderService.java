package com.otterworks.ticketing.orders.order;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.ticketing.orders.api.OrdersException;
import com.otterworks.ticketing.orders.outbox.OutboxMetrics;
import com.otterworks.ticketing.orders.outbox.OutboxRepository;
import com.otterworks.ticketing.orders.pricing.PricingService;
import com.otterworks.ticketing.orders.pricing.Quote;
import com.otterworks.ticketing.orders.seats.SeatsClient;
import com.otterworks.ticketing.orders.seats.SeatsClient.Hold;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Order placement. Holds seats through the seats service, prices the hold, then writes the order,
 * its items, its fees and the {@code order-placed} outbox row in ONE local transaction. Payment,
 * ticketing and seat state converge later through the /events inboxes.
 */
@Service
public class OrderService {

    public static final String ORDER_PLACED = "order-placed";
    public static final String CURRENCY = "USD";
    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    private final SeatsClient seats;
    private final PricingService pricing;
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final OutboxMetrics metrics;
    private final TransactionTemplate tx;
    private final ObjectMapper json;
    private final JdbcClient jdbc;
    private final Clock clock;

    public OrderService(SeatsClient seats, PricingService pricing, OrderRepository orders, OutboxRepository outbox,
                        OutboxMetrics metrics, TransactionTemplate tx, ObjectMapper json, JdbcClient jdbc, Clock clock) {
        this.seats = seats;
        this.pricing = pricing;
        this.orders = orders;
        this.outbox = outbox;
        this.metrics = metrics;
        this.tx = tx;
        this.json = json;
        this.jdbc = jdbc;
        this.clock = clock;
    }

    /** Legacy /api/purchase: hold best-available seats, then place. */
    public OrderRecord purchase(PlaceOrderRequest req) {
        Optional<OrderRecord> replay = replay(req);
        if (replay.isPresent()) {
            return replay.get();
        }
        Hold hold = seats.hold(req.performanceId(), req.quantity(), req.section(), req.normalisedEmail());
        long performanceId = hold.performanceId() != null ? hold.performanceId() : req.performanceId();
        return place(req, hold, performanceId);
    }

    /** /api/orders: place from a hold that already exists; 410 HOLD_EXPIRED when seats says it is not active. */
    public OrderRecord placeFromHold(PlaceOrderRequest req) {
        Optional<OrderRecord> replay = replay(req);
        if (replay.isPresent()) {
            return replay.get();
        }
        Hold hold = seats.hold(req.holdRef());
        if (!hold.active()) {
            throw new OrdersException("HOLD_EXPIRED", "hold " + req.holdRef() + " is " + hold.status());
        }
        if (hold.performanceId() == null) {
            throw new OrdersException("SEATS_UNAVAILABLE", "hold " + req.holdRef() + " carries no performanceId");
        }
        return place(req, hold, hold.performanceId());
    }

    private Optional<OrderRecord> replay(PlaceOrderRequest req) {
        String clientRef = req.clientRefOrNull();
        return clientRef == null ? Optional.empty() : orders.byClientRef(clientRef);
    }

    private OrderRecord place(PlaceOrderRequest req, Hold hold, long performanceId) {
        if (hold.seats().isEmpty()) {
            throw new OrdersException("SOLD_OUT", "hold " + hold.holdRef() + " carries no seats");
        }
        try {
            String orderRef = tx.execute(status -> writeOrder(req, hold, performanceId));
            metrics.placed();
            return orders.byRef(orderRef).orElseThrow();
        } catch (DuplicateKeyException e) {
            // two concurrent placements with the same clientRef: the first one wins, this one replays it
            return replay(req).orElseThrow(() -> e);
        }
    }

    private String writeOrder(PlaceOrderRequest req, Hold hold, long performanceId) {
        Quote quote = pricing.quote(performanceId, hold, req.promoCode(), req.deliveryOrDefault());
        String orderRef = Refs.next("BO");
        OffsetDateTime placedAt = OffsetDateTime.now(clock).withOffsetSameInstant(ZoneOffset.UTC);
        long orderId = orders.insertOrder(orderRef, req, hold.holdRef(), hold.expiresAt(), quote, placedAt);
        orders.insertItems(orderId, quote.lines());
        orders.insertFees(orderId, quote.fees());
        if (quote.promoCodeId() != null) {
            orders.incrementPromoUse(quote.promoCodeId());
        }
        Performance perf = jdbc.sql("""
                        SELECT e.title, p.starts_at, v.name FROM performances p
                        JOIN events e ON e.id = p.event_id JOIN venues v ON v.id = p.venue_id WHERE p.id = :id""")
                .param("id", performanceId)
                .query((rs, i) -> new Performance(rs.getString(1), OrderRepository.utc(rs.getTimestamp(2)), rs.getString(3)))
                .optional()
                .orElseThrow(() -> new OrdersException("NOT_FOUND", "performance " + performanceId + " not found"));
        outbox.append(orderRef, ORDER_PLACED, orderRef,
                toJson(orderPlacedPayload(orderRef, req, hold, performanceId, perf, quote, placedAt)));
        return orderRef;
    }

    Map<String, Object> orderPlacedPayload(String orderRef, PlaceOrderRequest req, Hold hold, long performanceId,
                                           Performance perf, Quote quote, OffsetDateTime placedAt) {
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("orderRef", orderRef);
        p.put("clientRef", req.clientRefOrNull());
        p.put("customerEmail", req.normalisedEmail());
        p.put("performanceId", performanceId);
        p.put("eventTitle", perf.eventTitle());
        p.put("venueName", perf.venueName());
        p.put("startsAt", iso(perf.startsAt()));
        p.put("holdRef", hold.holdRef());
        p.put("holdExpiresAt", iso(hold.expiresAt()));
        p.put("channel", req.channel());
        List<Map<String, Object>> items = new ArrayList<>();
        for (Quote.Line line : quote.lines()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("seatInventoryId", line.seatInventoryId());
            item.put("priceZoneId", line.priceZoneId());
            item.put("zoneCode", line.zoneCode());
            item.put("zoneName", line.zoneName());
            item.put("section", line.section());
            item.put("rowLabel", line.rowLabel());
            item.put("seatNumber", line.seatNumber());
            item.put("priceCents", line.priceCents());
            items.add(item);
        }
        p.put("items", items);
        List<Map<String, Object>> fees = new ArrayList<>();
        for (Quote.Fee fee : quote.fees()) {
            Map<String, Object> f = new LinkedHashMap<>();
            f.put("feeType", fee.feeType());
            f.put("amountCents", fee.amountCents());
            fees.add(f);
        }
        p.put("fees", fees);
        p.put("subtotalCents", quote.subtotalCents());
        p.put("feesCents", quote.feesCents());
        p.put("totalCents", quote.totalCents());
        p.put("currency", CURRENCY);
        p.put("cardLast4", req.cardLast4OrDefault());
        p.put("placedAt", iso(placedAt));
        return p;
    }

    public Optional<OrderRecord> find(String orderRef) {
        return orders.byRef(orderRef);
    }

    public Map<String, Object> view(String orderRef) {
        OrderRecord o = orders.byRef(orderRef)
                .orElseThrow(() -> new OrdersException("NOT_FOUND", orderRef));
        return OrderView.of(o, orders.items(o.id()), orders.fees(o.id()));
    }

    private String toJson(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("cannot serialise order-placed payload", e);
        }
    }

    public static String iso(OffsetDateTime t) {
        return t == null ? null : ISO.format(t.withOffsetSameInstant(ZoneOffset.UTC));
    }

    record Performance(String eventTitle, OffsetDateTime startsAt, String venueName) {
    }
}

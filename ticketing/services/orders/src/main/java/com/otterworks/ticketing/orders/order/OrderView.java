package com.otterworks.ticketing.orders.order;

import com.otterworks.ticketing.orders.pricing.Quote;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Response shapes that mirror the monolith's PurchaseResource. */
public final class OrderView {

    private OrderView() {
    }

    /** {orderRef,status,totalCents,tickets,paymentOutcome} — the purchase summary. */
    public static Map<String, Object> summary(OrderRecord o, long tickets) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("orderRef", o.orderRef());
        m.put("status", o.status());
        m.put("totalCents", o.totalCents());
        m.put("tickets", tickets);
        m.put("paymentOutcome", o.paymentOutcome());
        return m;
    }

    /** GET /api/orders/{ref}: snake_case order columns + items[] + fees[] + paymentOutcome, as before. */
    public static Map<String, Object> of(OrderRecord o, List<OrderItemRecord> items, List<Quote.Fee> fees) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("order_ref", o.orderRef());
        m.put("client_ref", o.clientRef());
        m.put("status", o.status());
        m.put("subtotal_cents", o.subtotalCents());
        m.put("fees_cents", o.feesCents());
        m.put("total_cents", o.totalCents());
        m.put("channel", o.channel());
        m.put("email", o.customerEmail());
        m.put("performance_id", o.performanceId());
        m.put("hold_ref", o.holdRef());
        m.put("event_title", o.eventTitle());
        m.put("starts_at", OrderService.iso(o.startsAt()));
        m.put("venue_name", o.venueName());
        m.put("created_at", OrderService.iso(o.createdAt()));
        m.put("updated_at", OrderService.iso(o.updatedAt()));
        List<Map<String, Object>> itemList = new ArrayList<>();
        for (OrderItemRecord it : items) {
            Map<String, Object> i = new LinkedHashMap<>();
            i.put("price_cents", it.priceCents());
            i.put("section", it.section());
            i.put("row_label", it.rowLabel());
            i.put("seat_number", it.seatNumber());
            i.put("zone", it.zoneName());
            i.put("zone_code", it.zoneCode());
            i.put("seat_inventory_id", it.seatInventoryId());
            i.put("ticket_code", it.ticketCode());
            itemList.add(i);
        }
        m.put("items", itemList);
        List<Map<String, Object>> feeList = new ArrayList<>();
        for (Quote.Fee fee : fees) {
            Map<String, Object> f = new LinkedHashMap<>();
            f.put("fee_type", fee.feeType());
            f.put("amount_cents", fee.amountCents());
            feeList.add(f);
        }
        m.put("fees", feeList);
        m.put("paymentOutcome", o.paymentOutcome());
        m.put("tickets", items.stream().filter(it -> it.ticketCode() != null).count());
        return m;
    }
}

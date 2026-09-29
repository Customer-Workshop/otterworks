package com.otterworks.ticketing.orders.order;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.ticketing.orders.pricing.Quote;
import com.otterworks.ticketing.orders.seats.SeatsClient;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrderPlacedPayloadTest {

    @Test
    void payloadCarriesEveryContractFieldInOrder() throws Exception {
        OrderService service = new OrderService(null, null, null, null, null, null, new ObjectMapper(), null, Clock.systemUTC());
        PlaceOrderRequest req = new PlaceOrderRequest(1L, null, "Payload@Example.Test", 2, null, null, null, null,
                "k6-42", "API");
        OffsetDateTime expires = OffsetDateTime.of(2026, 1, 1, 12, 10, 0, 0, ZoneOffset.UTC);
        SeatsClient.Hold hold = new SeatsClient.Hold("HD-PAYLOAD001", 1L, "ACTIVE", true, expires, List.of(), List.of());
        Quote quote = new Quote(1, List.of(
                new Quote.Line(1001, 1, "P1", "Premium", "A01", "R01", 1, 18900),
                new Quote.Line(1002, 1, "P1", "Premium", "A01", "R01", 2, 18900)),
                37800, 4536, 500, 0, 5036, 42836, null, null, 1L);
        OffsetDateTime placedAt = OffsetDateTime.of(2026, 1, 1, 12, 0, 0, 0, ZoneOffset.ofHours(2));

        Map<String, Object> p = service.orderPlacedPayload("BO-PAYLOAD0001", req, hold, 1,
                new OrderService.Performance("Synthetic Event", expires.minusDays(1), "Synthetic Venue"), quote, placedAt);

        assertThat(p.keySet()).containsExactly("orderRef", "clientRef", "customerEmail", "performanceId", "eventTitle",
                "venueName", "startsAt", "holdRef", "holdExpiresAt", "channel", "items", "fees", "subtotalCents",
                "feesCents", "totalCents", "currency", "cardLast4", "placedAt");
        assertThat(p.get("customerEmail")).isEqualTo("payload@example.test");
        assertThat(p.get("placedAt")).isEqualTo("2026-01-01T10:00:00Z");
        assertThat(p.get("holdExpiresAt")).isEqualTo("2026-01-01T12:10:00Z");
        assertThat(p.get("currency")).isEqualTo("USD");
        assertThat(p.get("cardLast4")).isEqualTo("4242");
        @SuppressWarnings("unchecked")
        Map<String, Object> item = ((List<Map<String, Object>>) p.get("items")).get(0);
        assertThat(item.keySet()).containsExactly("seatInventoryId", "priceZoneId", "zoneCode", "zoneName", "section",
                "rowLabel", "seatNumber", "priceCents");
        @SuppressWarnings("unchecked")
        Map<String, Object> fee = ((List<Map<String, Object>>) p.get("fees")).get(0);
        assertThat(fee.keySet()).containsExactly("feeType", "amountCents");
        assertThat(new ObjectMapper().writeValueAsString(p)).contains("\"totalCents\":42836");
    }
}

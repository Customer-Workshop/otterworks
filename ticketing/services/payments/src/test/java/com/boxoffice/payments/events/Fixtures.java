package com.boxoffice.payments.events;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.time.Instant;
import java.util.List;

/** Synthetic order-placed records shaped like the orders service outbox, and the recorded monolith contracts. */
public final class Fixtures {

    public static final ObjectMapper JSON = new ObjectMapper().registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private Fixtures() {
    }

    public static JsonNode contract(String name) {
        try (InputStream in = Fixtures.class.getResourceAsStream("/contracts/" + name + ".json")) {
            if (in == null) {
                throw new IllegalArgumentException("no contract fixture " + name);
            }
            return JSON.readTree(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** Two seats in performance 1 at the seed's 20000-cent zone price + fees = 42836, the monolith's total. */
    public static OrderPlaced orderPlaced(String orderRef, String cardLast4, Instant holdExpiresAt) {
        Instant placedAt = Instant.parse("2026-09-29T00:00:00Z");
        return new OrderPlaced(orderRef, "client-" + orderRef, "fan00001@example.test", 1L,
                "Synthetic Symphony No. 1", "Otter Hall", "2026-10-10T19:30:00Z", "HLD-" + orderRef, holdExpiresAt, "API",
                List.of(new OrderPlaced.Item(101L, 1L, "A", "Orchestra", "A01", "A", 1, 20000L),
                        new OrderPlaced.Item(102L, 1L, "A", "Orchestra", "A01", "A", 2, 20000L)),
                List.of(new OrderPlaced.Fee("SERVICE", 2400L), new OrderPlaced.Fee("FACILITY", 436L)),
                40000L, 2836L, 42836L, "USD", cardLast4, placedAt);
    }
}

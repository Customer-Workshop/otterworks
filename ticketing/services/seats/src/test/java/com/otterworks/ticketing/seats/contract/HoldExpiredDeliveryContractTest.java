package com.otterworks.ticketing.seats.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.otterworks.ticketing.seats.support.SeededServiceTest;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/** The sweep delivers hold-expired to the orders inbox and retries a failed delivery on the next sweep. */
class HoldExpiredDeliveryContractTest extends SeededServiceTest {

    private static final HttpServer ORDERS = startOrders();
    private static final List<String> RECEIVED = new CopyOnWriteArrayList<>();
    private static final AtomicBoolean FAIL = new AtomicBoolean(false);

    private static HttpServer startOrders() {
        try {
            HttpServer s = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            s.createContext("/events/hold-expired", ex -> {
                String body = new String(ex.getRequestBody().readAllBytes());
                if (FAIL.get()) {
                    ex.sendResponseHeaders(503, -1);
                } else {
                    RECEIVED.add(body);
                    ex.sendResponseHeaders(200, -1);
                }
                ex.close();
            });
            s.start();
            return s;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @DynamicPropertySource
    static void ordersInbox(DynamicPropertyRegistry r) {
        r.add("seats.orders.enabled", () -> "true");
        r.add("seats.orders.base-url", () -> "http://127.0.0.1:" + ORDERS.getAddress().getPort());
    }

    @AfterAll
    static void stopOrders() {
        ORDERS.stop(0);
    }

    @Test
    void sweepPostsHoldExpiredToOrdersAndRetriesFailures() throws Exception {
        RECEIVED.clear();
        String ref = post("/api/holds", hold(1, 2, null)).getBody().get("holdRef").asText();
        jdbc.update("UPDATE seat_holds SET expires_at = now() - interval '1 minute' WHERE hold_ref = ?", ref);

        FAIL.set(true);
        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isEqualTo(1);
        assertThat(RECEIVED).isEmpty();
        assertThat(get("/stats").getBody().get("holdExpiredPending").asLong()).isEqualTo(1);
        // the hold is already EXPIRED and its seats AVAILABLE even though delivery failed
        assertThat(get("/api/holds/" + ref).getBody().get("status").asText()).isEqualTo("EXPIRED");
        assertThat(get("/api/performances/1/availability").getBody().get("held").asLong()).isZero();

        FAIL.set(false);
        assertThat(post("/api/holds/sweep", null).getBody().get("released").asInt()).isZero();
        assertThat(RECEIVED).hasSize(1);
        JsonNode payload = json.readTree(RECEIVED.get(0));
        assertThat(payload.get("holdRef").asText()).isEqualTo(ref);
        assertThat(payload.get("performanceId").asLong()).isEqualTo(1);
        assertThat(payload.get("seatInventoryIds")).hasSize(2);
        assertThat(get("/stats").getBody().get("holdExpiredPending").asLong()).isZero();

        // delivered once; a further sweep does not re-send
        post("/api/holds/sweep", null);
        assertThat(RECEIVED).hasSize(1);
    }
}

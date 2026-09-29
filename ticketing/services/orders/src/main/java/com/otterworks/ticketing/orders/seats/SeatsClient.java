package com.otterworks.ticketing.orders.seats;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.ticketing.orders.api.OrdersException;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/**
 * HTTP client for the seats service. Business errors ({@code {error,message}} with 4xx) are passed
 * through unchanged as {@link OrdersException}; transport failures become {@code SEATS_UNAVAILABLE}.
 */
@Component
public class SeatsClient {

    private final RestClient client;
    private final ObjectMapper json;

    public SeatsClient(RestClient seatsRestClient, ObjectMapper json) {
        this.client = seatsRestClient;
        this.json = json;
    }

    /** {@code POST /api/holds} — best-available hold. */
    public Hold hold(long performanceId, int quantity, String section, String customerEmail) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("performanceId", performanceId);
        body.put("quantity", quantity);
        if (section != null) {
            body.put("section", section);
        }
        if (customerEmail != null) {
            body.put("customerEmail", customerEmail);
        }
        JsonNode node = exchange(() -> client.post().uri("/api/holds")
                .contentType(MediaType.APPLICATION_JSON).body(body).retrieve().body(String.class));
        return parseHold(node);
    }

    /** {@code GET /api/holds/{holdRef}} — hold status. */
    public Hold hold(String holdRef) {
        JsonNode node = exchange(() -> client.get().uri("/api/holds/{ref}", holdRef).retrieve().body(String.class));
        return parseHold(node);
    }

    private JsonNode exchange(java.util.function.Supplier<String> call) {
        try {
            return json.readTree(call.get());
        } catch (RestClientResponseException e) {
            throw passThrough(e);
        } catch (ResourceAccessException e) {
            throw new OrdersException("SEATS_UNAVAILABLE", "seats service unreachable: " + e.getMessage());
        } catch (IOException e) {
            throw new OrdersException("SEATS_UNAVAILABLE", "seats service returned unreadable body");
        }
    }

    private OrdersException passThrough(RestClientResponseException e) {
        HttpStatusCode status = e.getStatusCode();
        String code = null;
        String message = null;
        try {
            JsonNode body = json.readTree(e.getResponseBodyAsString());
            code = body.path("error").asText(null);
            message = body.path("message").asText(null);
        } catch (IOException ignored) {
            // non-JSON error body: fall through to status-based defaults
        }
        if (status.is5xxServerError()) {
            return new OrdersException("SEATS_UNAVAILABLE", "seats service error " + status.value());
        }
        if (code == null) {
            code = status.value() == 404 ? "NOT_FOUND" : status.value() == 409 ? "SOLD_OUT"
                    : status.value() == 410 ? "HOLD_EXPIRED" : "BAD_REQUEST";
        }
        return new OrdersException(code, message == null ? code : message,
                org.springframework.http.HttpStatus.valueOf(status.value()));
    }

    Hold parseHold(JsonNode n) {
        List<HeldSeat> seats = new ArrayList<>();
        for (JsonNode s : n.path("seats")) {
            seats.add(new HeldSeat(
                    s.path("seatInventoryId").asLong(),
                    s.path("priceZoneId").asLong(),
                    s.path("zoneCode").asText(null),
                    s.path("zoneName").asText(null),
                    s.path("section").asText(null),
                    s.path("rowLabel").asText(null),
                    s.path("seatNumber").asInt()));
        }
        List<ZoneTally> tally = new ArrayList<>();
        for (JsonNode t : n.path("zoneTally")) {
            tally.add(new ZoneTally(t.path("priceZoneId").asLong(), t.path("notAvailable").asLong(),
                    t.path("total").asLong()));
        }
        JsonNode active = n.path("active");
        JsonNode status = n.path("status");
        boolean isActive = active.isBoolean() ? active.asBoolean()
                : status.isMissingNode() || "ACTIVE".equals(status.asText());
        JsonNode perf = n.path("performanceId");
        return new Hold(
                n.path("holdRef").asText(null),
                perf.isNumber() || perf.isTextual() ? perf.asLong() : null,
                status.asText("ACTIVE"),
                isActive,
                parseTime(n.path("expiresAt")),
                seats,
                tally);
    }

    private static OffsetDateTime parseTime(JsonNode node) {
        if (node.isMissingNode() || node.isNull()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(node.asText());
        } catch (Exception e) {
            return null;
        }
    }

    public record Hold(String holdRef, Long performanceId, String status, boolean active, OffsetDateTime expiresAt,
                       List<HeldSeat> seats, List<ZoneTally> zoneTally) {
    }

    public record HeldSeat(long seatInventoryId, long priceZoneId, String zoneCode, String zoneName, String section,
                           String rowLabel, int seatNumber) {
    }

    public record ZoneTally(long priceZoneId, long notAvailable, long total) {
    }
}

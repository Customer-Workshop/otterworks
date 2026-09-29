package com.otterworks.ticketing.orders.support;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * Builds seats-service responses that mirror what the real seats service returns for the same seed:
 * best-available seats come from the first (Premium, P1) rows of a section, and the zone tally is
 * taken after the hold so the held seats count as not available.
 */
public final class SeatsStub {

    private static final Map<String, long[]> ZONE_TOTALS = Map.of(
            // venue code -> seats per zone (P1, P2, P3): sections x rows in zone x seats per row
            "TLM", new long[]{10 * 10 * 40, 10 * 20 * 40, 10 * 20 * 40},
            "OSH", new long[]{4 * 6 * 20, 4 * 12 * 20, 4 * 12 * 20},
            "QFT", new long[]{3 * 4 * 20, 3 * 8 * 20, 3 * 8 * 20});

    private final JdbcClient jdbc;
    private long nextSeatInventoryId = 900_000;

    public SeatsStub(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public record Venue(long id, String code) {
    }

    public Venue venueOf(long performanceId) {
        return jdbc.sql("SELECT v.id, v.code FROM performances p JOIN venues v ON v.id = p.venue_id WHERE p.id = :id")
                .param("id", performanceId).query((rs, i) -> new Venue(rs.getLong(1), rs.getString(2))).single();
    }

    public long zoneId(long venueId, String zoneCode) {
        return jdbc.sql("SELECT id FROM price_zones WHERE venue_id = :v AND code = :c")
                .param("v", venueId).param("c", zoneCode).query(Long.class).single();
    }

    /** A fresh ACTIVE hold of {@code quantity} P1 seats, {@code alreadyNotAvailable} other seats gone in P1. */
    public Map<String, Object> hold(String holdRef, long performanceId, int quantity, String section,
                                    long alreadyNotAvailable) {
        Venue venue = venueOf(performanceId);
        long p1 = zoneId(venue.id(), "P1");
        String sectionCode = section != null ? section : switch (venue.code()) {
            case "TLM" -> "A01";
            case "OSH" -> "H1";
            default -> "T1";
        };
        List<Map<String, Object>> seats = new ArrayList<>();
        for (int n = 1; n <= quantity; n++) {
            Map<String, Object> s = new LinkedHashMap<>();
            s.put("seatInventoryId", nextSeatInventoryId++);
            s.put("section", sectionCode);
            s.put("rowLabel", "R01");
            s.put("seatNumber", n);
            s.put("priceZoneId", p1);
            s.put("zoneCode", "P1");
            s.put("zoneName", "Premium");
            seats.add(s);
        }
        long[] totals = ZONE_TOTALS.get(venue.code());
        List<Map<String, Object>> tally = new ArrayList<>();
        tally.add(tally(p1, alreadyNotAvailable + quantity, totals[0]));
        tally.add(tally(zoneId(venue.id(), "P2"), 0, totals[1]));
        tally.add(tally(zoneId(venue.id(), "P3"), 0, totals[2]));
        Map<String, Object> hold = new LinkedHashMap<>();
        hold.put("holdRef", holdRef);
        hold.put("performanceId", performanceId);
        hold.put("status", "ACTIVE");
        hold.put("active", true);
        hold.put("expiresAt", OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(10).toString());
        hold.put("seats", seats);
        hold.put("zoneTally", tally);
        return hold;
    }

    private static Map<String, Object> tally(long zoneId, long notAvailable, long total) {
        Map<String, Object> t = new LinkedHashMap<>();
        t.put("priceZoneId", zoneId);
        t.put("notAvailable", notAvailable);
        t.put("total", total);
        return t;
    }
}

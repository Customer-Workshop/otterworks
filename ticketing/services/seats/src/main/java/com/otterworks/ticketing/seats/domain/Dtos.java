package com.otterworks.ticketing.seats.domain;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class Dtos {

    private Dtos() {
    }

    public record HoldRequest(Long performanceId, Integer quantity, String section, String customerEmail) {
    }

    public record SeatView(long seatInventoryId, String section, String rowLabel, int seatNumber,
                           long priceZoneId, String zoneCode, String zoneName) {
    }

    public record ZoneTally(long priceZoneId, long notAvailable, long total) {
    }

    public record HoldCreated(String holdRef, long performanceId, Instant expiresAt,
                              List<SeatView> seats, List<ZoneTally> zoneTally) {
    }

    public record HoldView(String holdRef, long performanceId, String status, boolean active, Instant expiresAt,
                           String orderRef, List<SeatView> seats) {
    }

    public record Availability(long available, long held, long sold) {
    }

    public record SweepResult(int released) {
    }

    public record Stats(long seatsAvailable, long seatsHeld, long seatsSold, Map<String, Long> holdsByStatus,
                        long inboxEvents, long holdExpiredPending) {
    }

    public record HoldExpired(String holdRef, long performanceId, String orderRef, List<Long> seatInventoryIds,
                              Instant expiredAt) {
    }

    public record InboxResult(String event, String key, boolean applied, String detail) {
    }
}

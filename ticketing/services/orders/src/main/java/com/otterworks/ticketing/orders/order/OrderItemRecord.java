package com.otterworks.ticketing.orders.order;

public record OrderItemRecord(long seatInventoryId, long priceZoneId, long priceCents, String section,
                              String rowLabel, int seatNumber, String zoneCode, String zoneName, String ticketCode) {
}

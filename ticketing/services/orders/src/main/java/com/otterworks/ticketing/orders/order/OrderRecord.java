package com.otterworks.ticketing.orders.order;

import java.time.OffsetDateTime;

public record OrderRecord(long id, String orderRef, String clientRef, String customerEmail, long performanceId,
                          String holdRef, OffsetDateTime holdExpiresAt, String status, String paymentOutcome,
                          long subtotalCents, long feesCents, long totalCents, String channel, String cardLast4,
                          OffsetDateTime createdAt, OffsetDateTime updatedAt, String eventTitle,
                          OffsetDateTime startsAt, String venueName) {
}

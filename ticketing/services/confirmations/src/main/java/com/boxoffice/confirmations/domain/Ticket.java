package com.boxoffice.confirmations.domain;

import java.time.LocalDateTime;

public record Ticket(String ticketCode, String orderRef, long seatInventoryId, String barcode, LocalDateTime issuedAt) {
}

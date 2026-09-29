package com.boxoffice.confirmations.domain;

import java.time.LocalDateTime;

public record Confirmation(String orderRef, String holdRef, long performanceId, String channel, String recipient,
                           String subject, String body, String status, LocalDateTime sentAt, LocalDateTime createdAt) {
}

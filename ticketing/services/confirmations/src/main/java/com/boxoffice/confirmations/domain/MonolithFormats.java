package com.boxoffice.confirmations.domain;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;

/**
 * Renders values exactly as the monolith did when it built the confirmation e-mail
 * ({@code ConfirmationBean.confirm}): money via {@code Money.format}, timestamps via
 * {@code java.sql.Timestamp#toString()} of the {@code performances.starts_at} column.
 */
public final class MonolithFormats {

    private MonolithFormats() {
    }

    public static String money(long cents) {
        return String.format("$%,d.%02d", cents / 100, Math.abs(cents % 100));
    }

    /**
     * Accepts the {@code startsAt} the orders service carries in {@code payment-captured.order} in any of
     * the forms it may take (ISO offset date-time, ISO local date-time, or the monolith's own
     * {@code yyyy-MM-dd HH:mm:ss[.f]} rendering) and returns the monolith rendering.
     */
    public static String startsAt(String raw) {
        if (raw == null || raw.isBlank()) {
            return "-";
        }
        String s = raw.trim();
        try {
            return Timestamp.valueOf(OffsetDateTime.parse(s).atZoneSameInstant(ZoneOffset.UTC).toLocalDateTime()).toString();
        } catch (DateTimeParseException ignored) {
            // not an offset date-time
        }
        try {
            return Timestamp.valueOf(LocalDateTime.parse(s)).toString();
        } catch (DateTimeParseException ignored) {
            // not an ISO local date-time
        }
        try {
            return Timestamp.valueOf(s).toString();
        } catch (IllegalArgumentException ignored) {
            return s;
        }
    }

    public static String barcode(String ticketCode, String orderRef, long seatInventoryId) {
        return Integer.toHexString((ticketCode + orderRef).hashCode()) + "-" + seatInventoryId;
    }

    public static String subject(String eventTitle) {
        return "Your tickets for " + eventTitle;
    }

    public static String body(String orderRef, int ticketCount, String eventTitle, String venueName, String startsAt,
                              long totalCents) {
        return "Order " + orderRef + ": " + ticketCount + " ticket(s) for " + eventTitle + " at " + venueName + " on "
                + startsAt(startsAt) + ". Total " + money(totalCents) + ".";
    }
}

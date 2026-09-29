package com.boxoffice.confirmations.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

/**
 * {@code <token>-payment-captured} payload, produced by payments and POSTed to {@code /events/payment-captured}.
 * Field names are the shared contract from ticketing/docs/decomposition.json; unknown fields are ignored so
 * the producer may grow the payload.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PaymentCapturedEvent(
        @NotBlank String orderRef,
        String gatewayRef,
        Long amountCents,
        String currency,
        String cardLast4,
        Integer attemptNo,
        Long latencyMs,
        String capturedAt,
        @NotNull @Valid Order order) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Order(
            @NotBlank String customerEmail,
            @NotNull Long performanceId,
            @NotBlank String eventTitle,
            @NotBlank String venueName,
            String startsAt,
            String holdRef,
            @NotNull Long totalCents,
            @NotEmpty @Valid List<Item> items) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Item(
            @NotNull Long seatInventoryId,
            String section,
            String rowLabel,
            Integer seatNumber,
            String zoneCode) {
    }
}

package com.otterworks.ticketing.seats.unit;

import static org.assertj.core.api.Assertions.assertThat;

import com.otterworks.ticketing.seats.api.ApiExceptionHandler;
import com.otterworks.ticketing.seats.domain.SeatsException;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.mock.http.MockHttpInputMessage;

/** The monolith's PurchaseResource.fromBusiness mapping and error envelope. */
class SeatsExceptionTest {

    private final ApiExceptionHandler handler = new ApiExceptionHandler();

    @Test
    void codesMapToMonolithStatuses() {
        assertThat(SeatsException.notFound("x").status()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(SeatsException.badQuantity("x").status()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(SeatsException.badRequest("x").status()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(SeatsException.soldOut("x").status()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(SeatsException.soldOut("x").code()).isEqualTo("SOLD_OUT");
    }

    @Test
    void envelopeIsErrorAndMessage() {
        ResponseEntity<?> r = handler.business(SeatsException.badQuantity("quantity must be 1..8"));
        assertThat(r.getStatusCode().value()).isEqualTo(400);
        assertThat(r.getBody()).isEqualTo(java.util.Map.of("error", "BAD_QUANTITY", "message", "quantity must be 1..8"));
    }

    @Test
    void invalidJsonIsBadRequest() {
        var e = new HttpMessageNotReadableException("boom", new MockHttpInputMessage(new byte[0]));
        ResponseEntity<?> r = handler.unreadable(e);
        assertThat(r.getStatusCode().value()).isEqualTo(400);
        assertThat(r.getBody()).isEqualTo(java.util.Map.of("error", "BAD_REQUEST", "message", "invalid JSON"));
    }
}

package com.otterworks.ticketing.orders.api;

import org.springframework.http.HttpStatus;

/** Business error carrying the legacy {@code {error, message}} code and its HTTP status. */
public class OrdersException extends RuntimeException {

    private final String code;
    private final HttpStatus status;

    public OrdersException(String code, String message) {
        this(code, message, statusFor(code));
    }

    public OrdersException(String code, String message, HttpStatus status) {
        super(message);
        this.code = code;
        this.status = status;
    }

    public String code() {
        return code;
    }

    public HttpStatus status() {
        return status;
    }

    /** Same mapping as the monolith's PurchaseResource. */
    public static HttpStatus statusFor(String code) {
        return switch (code) {
            case "SOLD_OUT" -> HttpStatus.CONFLICT;
            case "NOT_FOUND" -> HttpStatus.NOT_FOUND;
            case "BAD_QUANTITY", "BAD_REQUEST" -> HttpStatus.BAD_REQUEST;
            case "HOLD_EXPIRED" -> HttpStatus.GONE;
            case "SEATS_UNAVAILABLE" -> HttpStatus.SERVICE_UNAVAILABLE;
            default -> HttpStatus.INTERNAL_SERVER_ERROR;
        };
    }
}

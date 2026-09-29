package com.otterworks.ticketing.seats.domain;

import org.springframework.http.HttpStatus;

/** Business error with the monolith's error codes; mapped to {@code {"error":code,"message":...}}. */
public class SeatsException extends RuntimeException {

    private final String code;
    private final HttpStatus status;

    public SeatsException(String code, HttpStatus status, String message) {
        super(message);
        this.code = code;
        this.status = status;
    }

    public static SeatsException notFound(String message) {
        return new SeatsException("NOT_FOUND", HttpStatus.NOT_FOUND, message);
    }

    public static SeatsException badQuantity(String message) {
        return new SeatsException("BAD_QUANTITY", HttpStatus.BAD_REQUEST, message);
    }

    public static SeatsException badRequest(String message) {
        return new SeatsException("BAD_REQUEST", HttpStatus.BAD_REQUEST, message);
    }

    public static SeatsException soldOut(String message) {
        return new SeatsException("SOLD_OUT", HttpStatus.CONFLICT, message);
    }

    public String code() {
        return code;
    }

    public HttpStatus status() {
        return status;
    }
}

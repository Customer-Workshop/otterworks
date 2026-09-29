package com.boxoffice.confirmations.events;

/** The confirmation is committed but a downstream (Kafka or an inbox) did not accept it; the caller must retry. */
public class DeliveryException extends RuntimeException {

    private final String target;

    public DeliveryException(String target, String message, Throwable cause) {
        super(target + ": " + message, cause);
        this.target = target;
    }

    public String target() {
        return target;
    }
}

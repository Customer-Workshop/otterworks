package com.boxoffice.confirmations.domain;

/** Raised when two inbox requests for the same order race past the existence check; the loser replays. */
public class DuplicateOrderException extends RuntimeException {

    public DuplicateOrderException(String orderRef, Throwable cause) {
        super("confirmation already exists for " + orderRef, cause);
    }
}

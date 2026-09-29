package com.boxoffice.confirmations.api;

public class NotFoundException extends RuntimeException {

    public NotFoundException(String ref) {
        super(ref);
    }
}

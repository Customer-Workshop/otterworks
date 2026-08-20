package com.otterworks.legacyportal.common;

/** Thrown when an authenticated caller asks for a resource belonging to another user. */
public class ForbiddenException extends RuntimeException {

    public ForbiddenException(String message) {
        super(message);
    }
}

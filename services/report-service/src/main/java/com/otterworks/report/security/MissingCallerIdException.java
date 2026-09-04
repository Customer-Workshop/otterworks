package com.otterworks.report.security;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/**
 * Thrown when a user-scoped route is called without the gateway-injected
 * {@code X-User-ID} header.
 */
@ResponseStatus(value = HttpStatus.UNAUTHORIZED, reason = "Missing X-User-ID header")
public class MissingCallerIdException extends RuntimeException {

    public MissingCallerIdException() {
        super("Missing X-User-ID header");
    }
}

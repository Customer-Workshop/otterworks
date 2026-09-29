package com.boxoffice.common;

import jakarta.ejb.ApplicationException;

@ApplicationException(rollback = true)
public class BoxOfficeException extends RuntimeException {

    private final String code;

    public BoxOfficeException(String message) {
        this("ERROR", message);
    }

    public BoxOfficeException(String code, String message) {
        super(message);
        this.code = code;
    }

    public BoxOfficeException(String message, Throwable cause) {
        super(message, cause);
        this.code = "ERROR";
    }

    public String getCode() {
        return code;
    }
}

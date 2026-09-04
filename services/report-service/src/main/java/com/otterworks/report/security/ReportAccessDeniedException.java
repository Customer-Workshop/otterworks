package com.otterworks.report.security;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/**
 * Thrown when an authenticated caller acts on a report they do not own.
 */
@ResponseStatus(value = HttpStatus.FORBIDDEN, reason = "Report belongs to another user")
public class ReportAccessDeniedException extends RuntimeException {

    public ReportAccessDeniedException(Long reportId, String callerId) {
        super("Caller " + callerId + " is not the owner of report " + reportId);
    }

    public ReportAccessDeniedException(String message) {
        super(message);
    }
}

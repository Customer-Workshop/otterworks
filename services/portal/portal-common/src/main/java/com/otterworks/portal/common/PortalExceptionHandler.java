package com.otterworks.portal.common;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Byte-compatible port of the monolith's {@code GlobalExceptionHandler}.
 *
 * <p>Two envelopes exist on the legacy wire and both must survive extraction:
 *
 * <ul>
 *   <li><b>legacy</b> — {@code {"error","message"}}, produced here for
 *       {@link NoSuchElementException} and {@link IllegalArgumentException};
 *   <li><b>default</b> — {@code {"timestamp","status","error","path"}}, produced by Spring's
 *       own error handling for bean validation, unreadable bodies, 404, 405 and 500.
 * </ul>
 *
 * <p>Deliberately does <b>not</b> extend {@code ResponseEntityExceptionHandler}: doing so would
 * capture the framework exceptions and replace the default envelope, breaking parity.
 *
 * <p>Parameter and path-variable conversion failures land here by cause unwrapping —
 * {@code MethodArgumentTypeMismatchException} is unhandled, so Spring retries with its cause,
 * which is a {@link NumberFormatException} / {@link IllegalArgumentException}. That is why
 * {@code GET /api/announcements/abc} returns the legacy envelope with the message
 * {@code For input string: "abc"}. It is behaviour, not an accident; parity suites pin it.
 */
@RestControllerAdvice
public class PortalExceptionHandler {

    @ExceptionHandler(NoSuchElementException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(NoSuchElementException ex) {
        return error(HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException ex) {
        return error(HttpStatus.BAD_REQUEST, ex.getMessage());
    }

    private ResponseEntity<Map<String, String>> error(HttpStatus status, String message) {
        Map<String, String> body = new LinkedHashMap<>();
        body.put("error", status.getReasonPhrase());
        body.put("message", message);
        return ResponseEntity.status(status).body(body);
    }
}

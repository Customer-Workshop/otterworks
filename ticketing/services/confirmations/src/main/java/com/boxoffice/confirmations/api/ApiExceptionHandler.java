package com.boxoffice.confirmations.api;

import com.boxoffice.confirmations.domain.DuplicateOrderException;
import com.boxoffice.confirmations.events.DeliveryException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Same error envelope as the monolith's kiosk API: {@code {"error": CODE, "message": text}}. */
@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<Map<String, Object>> notFound(NotFoundException e) {
        return error(HttpStatus.NOT_FOUND, "NOT_FOUND", e.getMessage());
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, HttpMessageNotReadableException.class})
    public ResponseEntity<Map<String, Object>> badRequest(Exception e) {
        String msg = e instanceof MethodArgumentNotValidException v
                ? v.getBindingResult().getFieldErrors().stream()
                        .map(f -> f.getField() + " " + f.getDefaultMessage()).sorted().reduce((a, b) -> a + "; " + b).orElse("invalid")
                : "invalid JSON";
        return error(HttpStatus.BAD_REQUEST, "BAD_REQUEST", msg);
    }

    /** Tickets are committed; the event did not reach every consumer. payments retries and the replay re-delivers. */
    @ExceptionHandler(DeliveryException.class)
    public ResponseEntity<Map<String, Object>> deliveryFailed(DeliveryException e) {
        log.warn("delivery failed: {}", e.getMessage());
        Map<String, Object> body = envelope("DELIVERY_FAILED", e.getMessage());
        body.put("target", e.target());
        body.put("retryable", true);
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(body);
    }

    @ExceptionHandler(DuplicateOrderException.class)
    public ResponseEntity<Map<String, Object>> duplicate(DuplicateOrderException e) {
        return error(HttpStatus.CONFLICT, "DUPLICATE", e.getMessage());
    }

    private static ResponseEntity<Map<String, Object>> error(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(envelope(code, message));
    }

    private static Map<String, Object> envelope(String code, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", code);
        body.put("message", message);
        return body;
    }
}

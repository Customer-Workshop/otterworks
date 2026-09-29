package com.otterworks.ticketing.seats.api;

import com.otterworks.ticketing.seats.domain.SeatsException;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Same error envelope as the monolith's PurchaseResource: {"error": CODE, "message": text}. */
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(SeatsException.class)
    public ResponseEntity<Map<String, String>> business(SeatsException e) {
        return ResponseEntity.status(e.status()).body(Map.of("error", e.code(), "message", e.getMessage()));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(HttpMessageNotReadableException e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", "BAD_REQUEST", "message", "invalid JSON"));
    }
}

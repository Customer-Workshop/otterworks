package com.otterworks.auth.exception;

import io.jsonwebtoken.JwtException;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<ApiErrorResponse> handleIllegalArgument(IllegalArgumentException ex) {
    return buildErrorResponse(HttpStatus.BAD_REQUEST, "BAD_REQUEST", ex.getMessage());
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<ApiErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
    String errors =
        ex.getBindingResult().getFieldErrors().stream()
            .map(err -> err.getField() + ": " + err.getDefaultMessage())
            .collect(Collectors.joining(", "));
    return buildErrorResponse(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", errors);
  }

  @ExceptionHandler(JwtException.class)
  public ResponseEntity<ApiErrorResponse> handleJwtException(JwtException ex) {
    return buildErrorResponse(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "Invalid or expired token");
  }

  @ExceptionHandler(AccessDeniedException.class)
  public ResponseEntity<ApiErrorResponse> handleAccessDenied(AccessDeniedException ex) {
    return buildErrorResponse(HttpStatus.FORBIDDEN, "FORBIDDEN", "Access denied");
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<ApiErrorResponse> handleGeneral(Exception ex) {
    log.error("Unhandled exception", ex);
    return buildErrorResponse(
        HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Internal server error");
  }

  private ResponseEntity<ApiErrorResponse> buildErrorResponse(
      HttpStatus status, String code, String message) {
    return ResponseEntity.status(status).body(ApiErrorResponse.of(code, message, status.value()));
  }
}

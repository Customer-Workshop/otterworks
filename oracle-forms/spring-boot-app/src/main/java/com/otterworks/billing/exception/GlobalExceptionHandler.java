package com.otterworks.billing.exception;

import com.otterworks.billing.dto.Dtos.ErrorResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

  @ExceptionHandler(ValidationException.class)
  public ResponseEntity<ErrorResponse> handleValidation(ValidationException ex) {
    return ResponseEntity.badRequest().body(new ErrorResponse(ex.getField(), ex.getMessage()));
  }

  @ExceptionHandler(NotFoundException.class)
  public ResponseEntity<ErrorResponse> handleNotFound(NotFoundException ex) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(new ErrorResponse("id", ex.getMessage()));
  }

  @ExceptionHandler(NotImplementedException.class)
  public ResponseEntity<ErrorResponse> handleNotImplemented(NotImplementedException ex) {
    return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED)
        .body(new ErrorResponse("endpoint", ex.getMessage()));
  }
}

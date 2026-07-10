package com.otterworks.billing.exception;

/** Raised when a request violates a validation rule derived from a Forms trigger. */
public class ValidationException extends RuntimeException {
  private final String field;

  public ValidationException(String field, String message) {
    super(message);
    this.field = field;
  }

  public String getField() {
    return field;
  }
}

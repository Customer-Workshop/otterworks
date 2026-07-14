package com.otterworks.auth.exception;

public record ApiErrorResponse(ApiError error) {

  public record ApiError(String code, String message, int status) {}

  public static ApiErrorResponse of(String code, String message, int status) {
    return new ApiErrorResponse(new ApiError(code, message, status));
  }
}

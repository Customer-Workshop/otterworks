package com.otterworks.auth.exception;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.error.ErrorController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiErrorController implements ErrorController {

  @RequestMapping("/error")
  public ResponseEntity<ApiErrorResponse> error(HttpServletRequest request) {
    int status = status(request);
    HttpStatus httpStatus = HttpStatus.resolve(status);
    String message = httpStatus == null ? "Request failed" : httpStatus.getReasonPhrase();
    return ResponseEntity.status(status).body(ApiErrorResponse.of(code(status), message, status));
  }

  @RequestMapping("/api/v1/auth/**")
  public ResponseEntity<ApiErrorResponse> authRouteNotFound() {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(
            ApiErrorResponse.of(
                "NOT_FOUND", HttpStatus.NOT_FOUND.getReasonPhrase(), HttpStatus.NOT_FOUND.value()));
  }

  private int status(HttpServletRequest request) {
    Object value = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
    return value instanceof Integer ? (Integer) value : HttpStatus.INTERNAL_SERVER_ERROR.value();
  }

  private String code(int status) {
    return switch (status) {
      case 400 -> "BAD_REQUEST";
      case 401 -> "UNAUTHORIZED";
      case 403 -> "FORBIDDEN";
      case 404 -> "NOT_FOUND";
      case 405 -> "METHOD_NOT_ALLOWED";
      case 409 -> "CONFLICT";
      case 413 -> "PAYLOAD_TOO_LARGE";
      case 422 -> "VALIDATION_ERROR";
      case 429 -> "RATE_LIMIT_EXCEEDED";
      case 500 -> "INTERNAL_ERROR";
      case 502 -> "BAD_GATEWAY";
      case 503 -> "SERVICE_UNAVAILABLE";
      default -> "HTTP_ERROR";
    };
  }
}

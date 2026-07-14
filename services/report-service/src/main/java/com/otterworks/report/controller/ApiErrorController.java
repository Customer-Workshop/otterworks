package com.otterworks.report.controller;

import com.otterworks.report.model.ApiErrorResponse;
import org.springframework.boot.web.servlet.error.ErrorController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.RequestDispatcher;
import javax.servlet.http.HttpServletRequest;

@RestController
public class ApiErrorController implements ErrorController {

    @RequestMapping("/error")
    public ResponseEntity<ApiErrorResponse> error(HttpServletRequest request) {
        int status = status(request);
        HttpStatus httpStatus = HttpStatus.resolve(status);
        String message = httpStatus == null ? "Request failed" : httpStatus.getReasonPhrase();
        return ResponseEntity.status(status)
                .body(ApiErrorResponse.of(code(status), message, status));
    }

    @RequestMapping("/api/v1/**")
    public ResponseEntity<ApiErrorResponse> apiRouteNotFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ApiErrorResponse.of(
                        "NOT_FOUND",
                        HttpStatus.NOT_FOUND.getReasonPhrase(),
                        HttpStatus.NOT_FOUND.value()));
    }

    private int status(HttpServletRequest request) {
        Object value = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
        return value instanceof Integer
                ? (Integer) value
                : HttpStatus.INTERNAL_SERVER_ERROR.value();
    }

    private String code(int status) {
        switch (status) {
            case 400:
                return "BAD_REQUEST";
            case 401:
                return "UNAUTHORIZED";
            case 403:
                return "FORBIDDEN";
            case 404:
                return "NOT_FOUND";
            case 405:
                return "METHOD_NOT_ALLOWED";
            case 409:
                return "CONFLICT";
            case 413:
                return "PAYLOAD_TOO_LARGE";
            case 422:
                return "VALIDATION_ERROR";
            case 429:
                return "RATE_LIMIT_EXCEEDED";
            case 500:
                return "INTERNAL_ERROR";
            case 502:
                return "BAD_GATEWAY";
            case 503:
                return "SERVICE_UNAVAILABLE";
            default:
                return "HTTP_ERROR";
        }
    }
}

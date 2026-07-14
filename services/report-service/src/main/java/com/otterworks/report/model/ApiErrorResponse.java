package com.otterworks.report.model;

public class ApiErrorResponse {

    private final ApiError error;

    public ApiErrorResponse(ApiError error) {
        this.error = error;
    }

    public ApiError getError() {
        return error;
    }

    public static ApiErrorResponse of(String code, String message, int status) {
        return new ApiErrorResponse(new ApiError(code, message, status));
    }

    public static class ApiError {

        private final String code;
        private final String message;
        private final int status;

        public ApiError(String code, String message, int status) {
            this.code = code;
            this.message = message;
            this.status = status;
        }

        public String getCode() {
            return code;
        }

        public String getMessage() {
            return message;
        }

        public int getStatus() {
            return status;
        }
    }
}

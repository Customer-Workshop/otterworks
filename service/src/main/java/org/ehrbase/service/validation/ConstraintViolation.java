package org.ehrbase.service.validation;

import java.util.Objects;

/**
 * Structured validation error for a billing code that failed FHIR terminology validation.
 */
public record ConstraintViolation(
        String aqlPath,
        String failedCode,
        String codeSystem,
        String billingProfile,
        String category,
        String message) {

    public ConstraintViolation {
        Objects.requireNonNull(aqlPath, "aqlPath must not be null");
        Objects.requireNonNull(failedCode, "failedCode must not be null");
        Objects.requireNonNull(codeSystem, "codeSystem must not be null");
        Objects.requireNonNull(billingProfile, "billingProfile must not be null");
        Objects.requireNonNull(category, "category must not be null");
        Objects.requireNonNull(message, "message must not be null");
    }
}

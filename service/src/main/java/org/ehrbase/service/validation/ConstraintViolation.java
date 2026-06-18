package org.ehrbase.service.validation;

/**
 * Structured result produced when a billing code fails FHIR terminology validation.
 *
 * @param path              archetype path of the failing element inside the Composition
 * @param failedCode        the code string that could not be validated
 * @param codeSystem        the terminology system URI of the failing code
 * @param billingProfile    the name of the billing profile under which the code was validated
 * @param category          the billing category (diagnosis, procedure, clinical-justification)
 * @param message           human-readable description of the violation
 */
public record ConstraintViolation(
        String path,
        String failedCode,
        String codeSystem,
        String billingProfile,
        BillingCategory category,
        String message
) {

    public ConstraintViolation {
        if (failedCode == null || failedCode.isBlank()) {
            throw new IllegalArgumentException("failedCode must not be blank");
        }
        if (codeSystem == null || codeSystem.isBlank()) {
            throw new IllegalArgumentException("codeSystem must not be blank");
        }
        if (billingProfile == null || billingProfile.isBlank()) {
            throw new IllegalArgumentException("billingProfile must not be blank");
        }
        if (category == null) {
            throw new IllegalArgumentException("category must not be null");
        }
    }
}

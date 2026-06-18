package org.ehrbase.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.model.Composition;
import org.ehrbase.service.validation.BillingCodeValidator;
import org.ehrbase.service.validation.ConstraintViolation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Top-level validation service that orchestrates all validation phases
 * for a {@link Composition}. Billing validation is opt-in and only runs
 * when at least one billing profile is enabled.
 */
@Service
public class ValidationServiceImp {

    private static final Logger log = LoggerFactory.getLogger(ValidationServiceImp.class);

    private final ExternalValidationProperties validationProperties;
    private final BillingCodeValidator billingCodeValidator;

    public ValidationServiceImp(
            ExternalValidationProperties validationProperties,
            BillingCodeValidator billingCodeValidator) {
        this.validationProperties = validationProperties;
        this.billingCodeValidator = billingCodeValidator;
    }

    /**
     * Validates a composition through all configured validation phases.
     *
     * <ol>
     *   <li>Standard structural / archetype validation (placeholder for existing logic)</li>
     *   <li>Billing code validation (opt-in, per enabled billing profile)</li>
     * </ol>
     *
     * @param composition the composition to validate
     * @return all constraint violations found across all validation phases
     * @throws IllegalArgumentException if composition is null
     */
    public List<ConstraintViolation> check(Composition composition) {
        if (composition == null) {
            throw new IllegalArgumentException("composition must not be null");
        }

        List<ConstraintViolation> allViolations = new ArrayList<>();

        // Phase 1: existing structural/archetype validation would go here
        log.debug("Running structural validation for composition {}", composition.uid());

        // Phase 2: billing code validation (opt-in)
        if (validationProperties.isEnabled()) {
            List<ConstraintViolation> billingViolations = runBillingValidation(composition);
            allViolations.addAll(billingViolations);
        } else {
            log.debug("External validation is disabled; skipping billing validation");
        }

        return List.copyOf(allViolations);
    }

    private List<ConstraintViolation> runBillingValidation(Composition composition) {
        Map<String, BillingProfile> profiles = validationProperties.getBillingProfiles();

        if (profiles.isEmpty()) {
            log.debug("No billing profiles configured; skipping billing validation");
            return List.of();
        }

        List<ConstraintViolation> violations = new ArrayList<>();

        for (var entry : profiles.entrySet()) {
            String profileName = entry.getKey();
            BillingProfile profile = entry.getValue();

            if (!profile.isEnabled()) {
                log.debug("Billing profile '{}' is disabled; skipping", profileName);
                continue;
            }

            log.info("Validating composition {} against billing profile '{}'",
                    composition.uid(), profileName);

            List<ConstraintViolation> profileViolations =
                    billingCodeValidator.validate(composition, profileName, profile);
            violations.addAll(profileViolations);
        }

        return violations;
    }
}

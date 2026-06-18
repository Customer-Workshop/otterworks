package org.ehrbase.service;

import java.util.List;
import java.util.UUID;
import org.ehrbase.service.model.Composition;
import org.ehrbase.service.validation.ConstraintViolation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Service for managing compositions including creation, retrieval, and validation.
 */
@Service
public class CompositionServiceImp {

    private static final Logger LOG = LoggerFactory.getLogger(CompositionServiceImp.class);

    private final ValidationServiceImp validationService;

    public CompositionServiceImp(ValidationServiceImp validationService) {
        this.validationService = validationService;
    }

    /**
     * Creates a new composition after validation.
     *
     * @param composition the composition to create
     * @return the UUID of the created composition
     * @throws CompositionValidationException if validation fails
     */
    public UUID create(Composition composition) {
        List<ConstraintViolation> violations = validationService.check(composition);

        if (!violations.isEmpty()) {
            LOG.warn("Composition validation failed with {} violations", violations.size());
            throw new CompositionValidationException(violations);
        }

        UUID uid = UUID.randomUUID();
        composition.setUid(uid);
        LOG.info("Created composition with uid {}", uid);
        return uid;
    }

    public static class CompositionValidationException extends RuntimeException {
        private final List<ConstraintViolation> violations;

        public CompositionValidationException(List<ConstraintViolation> violations) {
            super("Composition validation failed with " + violations.size() + " violation(s)");
            this.violations = List.copyOf(violations);
        }

        public List<ConstraintViolation> getViolations() {
            return violations;
        }
    }
}

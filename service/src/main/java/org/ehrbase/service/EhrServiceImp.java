package org.ehrbase.service;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.ehrbase.api.service.EhrService;
import org.ehrbase.service.repository.EhrRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Implementation of {@link EhrService} providing EHR existence checks,
 * queryable status enforcement, and patient-to-EHR resolution.
 */
@Service
public class EhrServiceImp implements EhrService {

    private static final Logger log = LoggerFactory.getLogger(EhrServiceImp.class);

    private final EhrRepository ehrRepository;

    public EhrServiceImp(EhrRepository ehrRepository) {
        this.ehrRepository = ehrRepository;
    }

    @Override
    public boolean checkEhrExistsAndIsQueryable(UUID ehrId) {
        if (ehrId == null) {
            return false;
        }

        if (!ehrRepository.exists(ehrId)) {
            log.debug("EHR {} does not exist", ehrId);
            return false;
        }

        Optional<Boolean> queryable = ehrRepository.fetchIsQueryable(ehrId);
        if (queryable.isEmpty()) {
            log.debug("EHR {} not found when fetching queryable status", ehrId);
            return false;
        }

        if (!queryable.get()) {
            log.debug("EHR {} exists but is not queryable; returning empty result", ehrId);
            return false;
        }

        return true;
    }

    @Override
    public List<UUID> resolvePatientEhrIds(String patientId) {
        if (patientId == null || patientId.isBlank()) {
            return List.of();
        }
        return ehrRepository.findEhrIdsByPatientId(patientId);
    }

    @Override
    public boolean ehrExists(UUID ehrId) {
        return ehrId != null && ehrRepository.exists(ehrId);
    }
}

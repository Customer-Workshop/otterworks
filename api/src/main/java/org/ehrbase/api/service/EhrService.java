package org.ehrbase.api.service;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Service interface for EHR-level operations including existence checks
 * and queryable status enforcement.
 */
public interface EhrService {

    /**
     * Checks that an EHR with the given identifier exists and is queryable.
     * If the EHR exists but is not queryable, returns {@code false} rather
     * than throwing an exception — callers should return an empty result set.
     *
     * @param ehrId the EHR identifier to check
     * @return {@code true} if the EHR exists and is queryable
     */
    boolean checkEhrExistsAndIsQueryable(UUID ehrId);

    /**
     * Resolves a patient identifier to zero or more EHR IDs.
     *
     * @param patientId external patient identifier
     * @return list of EHR IDs associated with the patient
     */
    List<UUID> resolvePatientEhrIds(String patientId);

    /**
     * Checks whether an EHR with the given ID exists.
     *
     * @param ehrId the EHR identifier
     * @return {@code true} if the EHR exists
     */
    boolean ehrExists(UUID ehrId);
}

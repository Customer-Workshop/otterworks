package org.ehrbase.api.service;

import org.hl7.fhir.r4.model.Bundle;

/**
 * Service interface for FHIR R4 ExplanationOfBenefit resource retrieval.
 * Maps openEHR composition data to FHIR EOB resources for claims/remittance
 * data exchange.
 */
public interface FhirEobService {

    /**
     * Searches for ExplanationOfBenefit resources associated with a patient.
     * Resolves the patient identifier to EHR IDs, enforces is_queryable for
     * each EHR, retrieves billing-relevant compositions, and maps them to
     * FHIR EOB resources.
     *
     * @param patientId the patient identifier to search by
     * @param count     maximum number of entries per page (null for default)
     * @param offset    zero-based offset for pagination (null for start)
     * @param baseUrl   the base URL for constructing pagination links
     * @return a FHIR Bundle of type searchset containing EOB resources
     */
    Bundle searchByPatient(String patientId, Integer count, Integer offset, String baseUrl);
}

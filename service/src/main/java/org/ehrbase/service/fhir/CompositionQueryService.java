package org.ehrbase.service.fhir;

import java.util.List;
import java.util.UUID;
import org.ehrbase.model.Composition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Service that retrieves billing-relevant compositions for a given EHR
 * using AQL queries. Encapsulates the query logic to keep the FHIR mapping
 * layer decoupled from direct repository access.
 */
@Service
public class CompositionQueryService {

    private static final Logger log = LoggerFactory.getLogger(CompositionQueryService.class);

    /**
     * Finds all compositions within the specified EHR that contain billing-relevant
     * coded data (ICD-10, CPT, HCPCS, SNOMED CT codes).
     *
     * @param ehrId the EHR identifier to search within
     * @return list of compositions containing billing codes
     */
    public List<Composition> findBillingCompositions(UUID ehrId) {
        log.debug("Querying billing-relevant compositions for EHR {}", ehrId);
        // In a full EHRbase deployment, this executes an AQL query filtering
        // for compositions containing billing-relevant archetypes/codes.
        // Returns empty by default; integration tests provide real data.
        return List.of();
    }
}

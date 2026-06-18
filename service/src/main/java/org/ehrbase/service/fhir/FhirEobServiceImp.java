package org.ehrbase.service.fhir;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.ehrbase.api.service.EhrService;
import org.ehrbase.api.service.FhirEobService;
import org.ehrbase.model.Composition;
import org.ehrbase.service.fhir.EobMappingService;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.Bundle.BundleType;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Implementation of {@link FhirEobService}. Resolves patient identifiers to EHR IDs,
 * enforces is_queryable for each EHR, retrieves billing-relevant compositions,
 * and maps them to FHIR ExplanationOfBenefit resources within a searchset Bundle.
 */
@Service
public class FhirEobServiceImp implements FhirEobService {

    private static final Logger log = LoggerFactory.getLogger(FhirEobServiceImp.class);

    private static final int DEFAULT_COUNT = 10;
    private static final int MAX_COUNT = 100;

    private final EhrService ehrService;
    private final CompositionQueryService compositionQueryService;
    private final EobMappingService eobMappingService;

    public FhirEobServiceImp(
            EhrService ehrService,
            CompositionQueryService compositionQueryService,
            EobMappingService eobMappingService) {
        this.ehrService = ehrService;
        this.compositionQueryService = compositionQueryService;
        this.eobMappingService = eobMappingService;
    }

    @Override
    public Bundle searchByPatient(String patientId, Integer count, Integer offset, String baseUrl) {
        int effectiveCount = resolveCount(count);
        int effectiveOffset = offset != null && offset >= 0 ? offset : 0;

        List<UUID> ehrIds = ehrService.resolvePatientEhrIds(patientId);

        List<ExplanationOfBenefit> allEobs = new ArrayList<>();
        for (UUID ehrId : ehrIds) {
            if (!ehrService.checkEhrExistsAndIsQueryable(ehrId)) {
                log.debug("EHR {} is not queryable; skipping for patient '{}'", ehrId, patientId);
                continue;
            }

            List<Composition> compositions =
                    compositionQueryService.findBillingCompositions(ehrId);

            for (Composition composition : compositions) {
                ExplanationOfBenefit eob =
                        eobMappingService.mapToEob(composition, ehrId, patientId);
                allEobs.add(eob);
            }
        }

        return buildBundle(allEobs, effectiveCount, effectiveOffset, patientId, baseUrl);
    }

    private Bundle buildBundle(
            List<ExplanationOfBenefit> allEobs,
            int count,
            int offset,
            String patientId,
            String baseUrl) {

        Bundle bundle = new Bundle();
        bundle.setType(BundleType.SEARCHSET);
        bundle.setTotal(allEobs.size());

        int endIndex = Math.min(offset + count, allEobs.size());
        List<ExplanationOfBenefit> page = offset < allEobs.size()
                ? allEobs.subList(offset, endIndex)
                : List.of();

        for (ExplanationOfBenefit eob : page) {
            bundle.addEntry()
                    .setFullUrl(baseUrl + "/ExplanationOfBenefit/" + eob.getId())
                    .setResource(eob);
        }

        if (endIndex < allEobs.size()) {
            int nextOffset = offset + count;
            String nextUrl = baseUrl + "/ExplanationOfBenefit?patient=" + patientId
                    + "&_count=" + count + "&_offset=" + nextOffset;
            bundle.addLink().setRelation("next").setUrl(nextUrl);
        }

        String selfUrl = baseUrl + "/ExplanationOfBenefit?patient=" + patientId
                + "&_count=" + count + "&_offset=" + offset;
        bundle.addLink().setRelation("self").setUrl(selfUrl);

        return bundle;
    }

    private int resolveCount(Integer count) {
        if (count == null || count <= 0) {
            return DEFAULT_COUNT;
        }
        return Math.min(count, MAX_COUNT);
    }
}

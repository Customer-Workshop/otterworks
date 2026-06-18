package com.otterworks.report.fhir;

import com.otterworks.report.model.ehr.Composition;
import com.otterworks.report.repository.ehr.CompositionRepository;
import com.otterworks.report.service.ehr.EhrService;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Service
public class FhirEobServiceImpl implements FhirEobService {

    private static final Logger logger = LoggerFactory.getLogger(FhirEobServiceImpl.class);

    private final EhrService ehrService;
    private final CompositionRepository compositionRepository;
    private final EobMappingService eobMappingService;

    public FhirEobServiceImpl(EhrService ehrService,
                              CompositionRepository compositionRepository,
                              EobMappingService eobMappingService) {
        this.ehrService = ehrService;
        this.compositionRepository = compositionRepository;
        this.eobMappingService = eobMappingService;
    }

    @Override
    public Bundle searchByPatient(String patientId, int count, int offset, String baseUrl) {
        List<UUID> queryableEhrIds = ehrService.getQueryableEhrIds(patientId);

        if (queryableEhrIds.isEmpty()) {
            logger.debug("No queryable EHRs found for patient: {}", patientId);
            String selfUrl = buildSelfUrl(baseUrl, patientId, count, offset);
            return eobMappingService.buildSearchBundle(
                    Collections.<ExplanationOfBenefit>emptyList(), 0, selfUrl, null);
        }

        int pageNumber = offset / Math.max(count, 1);
        PageRequest pageRequest = PageRequest.of(pageNumber, count,
                Sort.by(Sort.Direction.DESC, "commitTime"));

        Page<Composition> page = compositionRepository.findByEhrIdIn(queryableEhrIds, pageRequest);

        List<ExplanationOfBenefit> eobs = new ArrayList<>();
        for (Composition composition : page.getContent()) {
            eobs.add(eobMappingService.mapToEob(composition, patientId));
        }

        String selfUrl = buildSelfUrl(baseUrl, patientId, count, offset);
        String nextUrl = null;
        if (page.hasNext()) {
            int nextOffset = offset + count;
            nextUrl = buildSelfUrl(baseUrl, patientId, count, nextOffset);
        }

        return eobMappingService.buildSearchBundle(eobs, page.getTotalElements(),
                selfUrl, nextUrl);
    }

    private String buildSelfUrl(String baseUrl, String patientId, int count, int offset) {
        return baseUrl + "/ExplanationOfBenefit?patient=" + patientId
                + "&_count=" + count + "&_offset=" + offset;
    }
}

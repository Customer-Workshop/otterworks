package com.otterworks.report.service.ehr;

import com.otterworks.report.model.ehr.Ehr;
import com.otterworks.report.repository.ehr.EhrRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Service
public class EhrServiceImpl implements EhrService {

    private static final Logger logger = LoggerFactory.getLogger(EhrServiceImpl.class);

    private final EhrRepository ehrRepository;

    public EhrServiceImpl(EhrRepository ehrRepository) {
        this.ehrRepository = ehrRepository;
    }

    @Override
    public List<Ehr> findQueryableEhrsByPatient(String patientId) {
        return ehrRepository.findByPatientIdAndQueryableTrue(patientId);
    }

    @Override
    public boolean isQueryable(UUID ehrId) {
        Boolean queryable = ehrRepository.fetchIsQueryable(ehrId);
        if (queryable == null) {
            logger.warn("EHR not found: {}", ehrId);
            return false;
        }
        return queryable;
    }

    @Override
    public List<UUID> getQueryableEhrIds(String patientId) {
        List<Ehr> ehrs = findQueryableEhrsByPatient(patientId);
        if (ehrs.isEmpty()) {
            return Collections.emptyList();
        }
        List<UUID> ids = new ArrayList<>(ehrs.size());
        for (Ehr ehr : ehrs) {
            ids.add(ehr.getEhrId());
        }
        return ids;
    }
}

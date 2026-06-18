package com.otterworks.report.service.ehr;

import com.otterworks.report.model.ehr.Ehr;

import java.util.List;
import java.util.UUID;

public interface EhrService {

    List<Ehr> findQueryableEhrsByPatient(String patientId);

    boolean isQueryable(UUID ehrId);

    List<UUID> getQueryableEhrIds(String patientId);
}

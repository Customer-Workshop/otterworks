package com.otterworks.report.fhir;

import org.hl7.fhir.r4.model.Bundle;

public interface FhirEobService {

    Bundle searchByPatient(String patientId, int count, int offset, String baseUrl);
}

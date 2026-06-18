package com.otterworks.report.fhir;

import com.otterworks.report.model.ehr.Composition;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.DiagnosisComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ProcedureComponent;
import org.junit.Before;
import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.UUID;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class EobMappingServiceTest {

    private EobMappingService mappingService;

    @Before
    public void setUp() {
        mappingService = new EobMappingService();
    }

    @Test
    public void mapsIcd10ToDiagnosis() {
        Composition composition = buildComposition();
        composition.setDiagnosisCode("J06.9");
        composition.setDiagnosisDisplay("Acute upper respiratory infection, unspecified");
        composition.setDiagnosisSystem("http://hl7.org/fhir/sid/icd-10");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-1");

        assertFalse(eob.getDiagnosis().isEmpty());
        DiagnosisComponent diag = eob.getDiagnosis().get(0);
        assertEquals(1, diag.getSequence());
        assertEquals("J06.9",
                diag.getDiagnosisCodeableConcept().getCodingFirstRep().getCode());
        assertEquals("http://hl7.org/fhir/sid/icd-10",
                diag.getDiagnosisCodeableConcept().getCodingFirstRep().getSystem());
        assertEquals("Acute upper respiratory infection, unspecified",
                diag.getDiagnosisCodeableConcept().getCodingFirstRep().getDisplay());
    }

    @Test
    public void defaultsDiagnosisSystemToIcd10WhenNull() {
        Composition composition = buildComposition();
        composition.setDiagnosisCode("E11.65");
        composition.setDiagnosisDisplay("Type 2 diabetes mellitus with hyperglycemia");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-2");

        assertEquals("http://hl7.org/fhir/sid/icd-10",
                eob.getDiagnosis().get(0).getDiagnosisCodeableConcept()
                        .getCodingFirstRep().getSystem());
    }

    @Test
    public void mapsCptToProcedureAndItem() {
        Composition composition = buildComposition();
        composition.setProcedureCode("99213");
        composition.setProcedureDisplay("Office visit, established patient");
        composition.setProcedureSystem("http://www.ama-assn.org/go/cpt");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-3");

        assertFalse(eob.getProcedure().isEmpty());
        ProcedureComponent proc = eob.getProcedure().get(0);
        assertEquals("99213",
                proc.getProcedureCodeableConcept().getCodingFirstRep().getCode());
        assertEquals("http://www.ama-assn.org/go/cpt",
                proc.getProcedureCodeableConcept().getCodingFirstRep().getSystem());

        assertFalse(eob.getItem().isEmpty());
        assertEquals("99213",
                eob.getItem().get(0).getProductOrService().getCodingFirstRep().getCode());
    }

    @Test
    public void mapsHcpcsToProcedure() {
        Composition composition = buildComposition();
        composition.setProcedureCode("G0438");
        composition.setProcedureDisplay("Annual wellness visit, initial");
        composition.setProcedureSystem("https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-4");

        assertEquals("https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
                eob.getProcedure().get(0).getProcedureCodeableConcept()
                        .getCodingFirstRep().getSystem());
    }

    @Test
    public void handlesMissingOptionalFields() {
        Composition composition = buildComposition();

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-5");

        assertNotNull(eob);
        assertEquals(ExplanationOfBenefit.ExplanationOfBenefitStatus.ACTIVE, eob.getStatus());
        assertEquals(ExplanationOfBenefit.Use.CLAIM, eob.getUse());
        assertEquals("Patient/patient-5", eob.getPatient().getReference());
        assertTrue(eob.getDiagnosis().isEmpty());
        assertTrue(eob.getProcedure().isEmpty());
        assertTrue(eob.getItem().isEmpty());
        assertTrue(eob.getProvider().isEmpty());
        assertFalse(eob.hasFacility());
    }

    @Test
    public void stableIds() {
        UUID compositionId = UUID.fromString("550e8400-e29b-41d4-a716-446655440000");
        Composition composition = buildComposition();
        composition.setCompositionId(compositionId);

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-6");

        assertEquals("550e8400-e29b-41d4-a716-446655440000", eob.getId());
    }

    @Test
    public void stablePatientReference() {
        Composition composition = buildComposition();

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-99");

        assertEquals("Patient/patient-99", eob.getPatient().getReference());
    }

    @Test
    public void usesStartTimeAsCreatedWhenAvailable() {
        Composition composition = buildComposition();
        Date startTime = new Date(1700000000000L);
        Date commitTime = new Date(1700100000000L);
        composition.setStartTime(startTime);
        composition.setCommitTime(commitTime);

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-7");

        assertEquals(startTime, eob.getCreated());
    }

    @Test
    public void fallsBackToCommitTimeWhenStartTimeNull() {
        Composition composition = buildComposition();
        Date commitTime = new Date(1700100000000L);
        composition.setStartTime(null);
        composition.setCommitTime(commitTime);

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-8");

        assertEquals(commitTime, eob.getCreated());
    }

    @Test
    public void mapsInstitutionalEncounterType() {
        Composition composition = buildComposition();
        composition.setEncounterType("inpatient");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-9");

        assertEquals("institutional",
                eob.getType().getCodingFirstRep().getCode());
    }

    @Test
    public void mapsPharmacyEncounterType() {
        Composition composition = buildComposition();
        composition.setEncounterType("pharmacy");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-10");

        assertEquals("pharmacy",
                eob.getType().getCodingFirstRep().getCode());
    }

    @Test
    public void mapsProfessionalEncounterType() {
        Composition composition = buildComposition();
        composition.setEncounterType("outpatient");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-11");

        assertEquals("professional",
                eob.getType().getCodingFirstRep().getCode());
    }

    @Test
    public void buildSearchBundleSetsTypeAndTotal() {
        Bundle bundle = mappingService.buildSearchBundle(
                Collections.<ExplanationOfBenefit>emptyList(), 0,
                "http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=1",
                null);

        assertEquals(Bundle.BundleType.SEARCHSET, bundle.getType());
        assertEquals(0, bundle.getTotal());
    }

    @Test
    public void buildSearchBundleIncludesNextLink() {
        ExplanationOfBenefit eob = new ExplanationOfBenefit();
        eob.setId("test-id");

        Bundle bundle = mappingService.buildSearchBundle(
                Arrays.asList(eob), 5,
                "http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=1&_count=1&_offset=0",
                "http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=1&_count=1&_offset=1");

        assertEquals(2, bundle.getLink().size());
        assertEquals("self", bundle.getLink().get(0).getRelation());
        assertEquals("next", bundle.getLink().get(1).getRelation());
        assertEquals(1, bundle.getEntry().size());
    }

    @Test
    public void mapsProviderAndFacility() {
        Composition composition = buildComposition();
        composition.setProviderName("Dr. Smith");
        composition.setFacilityName("City Hospital");

        ExplanationOfBenefit eob = mappingService.mapToEob(composition, "patient-12");

        assertEquals("Dr. Smith", eob.getProvider().getDisplay());
        assertEquals("City Hospital", eob.getFacility().getDisplay());
    }

    private Composition buildComposition() {
        Composition c = new Composition();
        c.setCompositionId(UUID.randomUUID());
        c.setEhrId(UUID.randomUUID());
        c.setCommitTime(new Date());
        return c;
    }
}

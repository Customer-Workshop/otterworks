package com.otterworks.report.fhir;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.parser.IParser;
import com.otterworks.report.model.ehr.Composition;
import com.otterworks.report.model.ehr.Ehr;
import com.otterworks.report.repository.ehr.CompositionRepository;
import com.otterworks.report.repository.ehr.EhrRepository;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit4.SpringRunner;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Date;
import java.util.UUID;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@RunWith(SpringRunner.class)
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class FhirEobIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private EhrRepository ehrRepository;

    @Autowired
    private CompositionRepository compositionRepository;

    private final FhirContext fhirContext = FhirContext.forR4();

    @Before
    public void setUp() {
        compositionRepository.deleteAll();
        ehrRepository.deleteAll();
    }

    @Test
    public void fullFlowWithBillingComposition() throws Exception {
        String patientId = "integration-patient-1";
        UUID ehrId = UUID.randomUUID();

        Ehr ehr = new Ehr();
        ehr.setEhrId(ehrId);
        ehr.setPatientId(patientId);
        ehr.setQueryable(true);
        ehr.setCreatedAt(new Date());
        ehrRepository.save(ehr);

        UUID compositionId = UUID.randomUUID();
        Composition comp = new Composition();
        comp.setCompositionId(compositionId);
        comp.setEhrId(ehrId);
        comp.setEncounterType("inpatient");
        comp.setDiagnosisCode("J06.9");
        comp.setDiagnosisDisplay("Acute upper respiratory infection");
        comp.setDiagnosisSystem("http://hl7.org/fhir/sid/icd-10");
        comp.setProcedureCode("99213");
        comp.setProcedureDisplay("Office visit, established patient");
        comp.setProcedureSystem("http://www.ama-assn.org/go/cpt");
        comp.setProviderName("Dr. Test");
        comp.setFacilityName("Test Hospital");
        comp.setStartTime(new Date(1700000000000L));
        comp.setCommitTime(new Date());
        compositionRepository.save(comp);

        MvcResult result = mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", patientId)
                        .accept("application/fhir+json"))
                .andExpect(status().isOk())
                .andReturn();

        String responseBody = result.getResponse().getContentAsString();
        IParser parser = fhirContext.newJsonParser();
        Bundle bundle = parser.parseResource(Bundle.class, responseBody);

        assertEquals(Bundle.BundleType.SEARCHSET, bundle.getType());
        assertEquals(1, bundle.getTotal());
        assertEquals(1, bundle.getEntry().size());

        ExplanationOfBenefit eob = (ExplanationOfBenefit) bundle.getEntry().get(0).getResource();
        assertEquals(ExplanationOfBenefit.ExplanationOfBenefitStatus.ACTIVE, eob.getStatus());
        assertEquals("Patient/" + patientId, eob.getPatient().getReference());
        assertEquals("J06.9",
                eob.getDiagnosis().get(0).getDiagnosisCodeableConcept()
                        .getCodingFirstRep().getCode());
        assertEquals("99213",
                eob.getProcedure().get(0).getProcedureCodeableConcept()
                        .getCodingFirstRep().getCode());
    }

    @Test
    public void nonQueryableEhrReturnsNoBundleEntries() throws Exception {
        String patientId = "integration-patient-2";
        UUID ehrId = UUID.randomUUID();

        Ehr ehr = new Ehr();
        ehr.setEhrId(ehrId);
        ehr.setPatientId(patientId);
        ehr.setQueryable(false);
        ehr.setCreatedAt(new Date());
        ehrRepository.save(ehr);

        Composition comp = new Composition();
        comp.setCompositionId(UUID.randomUUID());
        comp.setEhrId(ehrId);
        comp.setDiagnosisCode("E11.65");
        comp.setCommitTime(new Date());
        compositionRepository.save(comp);

        MvcResult result = mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", patientId)
                        .accept("application/fhir+json"))
                .andExpect(status().isOk())
                .andReturn();

        Bundle bundle = fhirContext.newJsonParser()
                .parseResource(Bundle.class, result.getResponse().getContentAsString());

        assertEquals(0, bundle.getTotal());
        assertTrue(bundle.getEntry().isEmpty());
    }

    @Test
    public void fhirJsonParsesAsR4Bundle() throws Exception {
        String patientId = "integration-patient-3";
        UUID ehrId = UUID.randomUUID();

        Ehr ehr = new Ehr();
        ehr.setEhrId(ehrId);
        ehr.setPatientId(patientId);
        ehr.setQueryable(true);
        ehr.setCreatedAt(new Date());
        ehrRepository.save(ehr);

        Composition comp = new Composition();
        comp.setCompositionId(UUID.randomUUID());
        comp.setEhrId(ehrId);
        comp.setDiagnosisCode("I10");
        comp.setDiagnosisDisplay("Essential hypertension");
        comp.setProcedureCode("G0438");
        comp.setProcedureDisplay("Annual wellness visit");
        comp.setProcedureSystem("https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets");
        comp.setCommitTime(new Date());
        compositionRepository.save(comp);

        MvcResult result = mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", patientId)
                        .accept("application/fhir+json"))
                .andExpect(status().isOk())
                .andReturn();

        String json = result.getResponse().getContentAsString();
        assertNotNull(json);
        assertFalse(json.isEmpty());

        Bundle bundle = fhirContext.newJsonParser().parseResource(Bundle.class, json);
        assertNotNull(bundle);
        assertEquals("Bundle", bundle.fhirType());
        assertEquals(Bundle.BundleType.SEARCHSET, bundle.getType());
    }

    @Test
    public void paginationWithMultipleCompositions() throws Exception {
        String patientId = "integration-patient-4";
        UUID ehrId = UUID.randomUUID();

        Ehr ehr = new Ehr();
        ehr.setEhrId(ehrId);
        ehr.setPatientId(patientId);
        ehr.setQueryable(true);
        ehr.setCreatedAt(new Date());
        ehrRepository.save(ehr);

        for (int i = 0; i < 5; i++) {
            Composition comp = new Composition();
            comp.setCompositionId(UUID.randomUUID());
            comp.setEhrId(ehrId);
            comp.setDiagnosisCode("J0" + i + ".0");
            comp.setCommitTime(new Date(System.currentTimeMillis() - i * 3600000L));
            compositionRepository.save(comp);
        }

        MvcResult result = mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", patientId)
                        .param("_count", "2")
                        .param("_offset", "0")
                        .accept("application/fhir+json"))
                .andExpect(status().isOk())
                .andReturn();

        Bundle bundle = fhirContext.newJsonParser()
                .parseResource(Bundle.class, result.getResponse().getContentAsString());

        assertEquals(5, bundle.getTotal());
        assertEquals(2, bundle.getEntry().size());

        boolean hasNext = false;
        for (Bundle.BundleLinkComponent link : bundle.getLink()) {
            if ("next".equals(link.getRelation())) {
                hasNext = true;
                assertTrue(link.getUrl().contains("_offset=2"));
            }
        }
        assertTrue("Expected next link for pagination", hasNext);
    }
}

package com.otterworks.report.controller.fhir;

import com.otterworks.report.fhir.FhirEobService;
import com.otterworks.report.fhir.FhirJsonService;
import com.otterworks.report.fhir.FhirMediaType;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit4.SpringRunner;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@RunWith(SpringRunner.class)
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class FhirEobControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private FhirEobService fhirEobService;

    @Test
    public void missingPatientParamReturns400() throws Exception {
        mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .accept(FhirMediaType.APPLICATION_FHIR_JSON_VALUE))
                .andExpect(status().isBadRequest());
    }

    @Test
    public void returnsFhirJsonContentType() throws Exception {
        Bundle emptyBundle = new Bundle();
        emptyBundle.setType(Bundle.BundleType.SEARCHSET);
        emptyBundle.setTotal(0);
        emptyBundle.addLink().setRelation("self")
                .setUrl("http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=p1&_count=10&_offset=0");

        when(fhirEobService.searchByPatient(eq("p1"), anyInt(), anyInt(), anyString()))
                .thenReturn(emptyBundle);

        mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", "p1")
                        .accept(FhirMediaType.APPLICATION_FHIR_JSON_VALUE))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("application/fhir+json"))
                .andExpect(jsonPath("$.resourceType", is("Bundle")))
                .andExpect(jsonPath("$.type", is("searchset")))
                .andExpect(jsonPath("$.total", is(0)));
    }

    @Test
    public void emptyBundleWhenNoPatientEhrCompositions() throws Exception {
        Bundle emptyBundle = new Bundle();
        emptyBundle.setType(Bundle.BundleType.SEARCHSET);
        emptyBundle.setTotal(0);
        emptyBundle.addLink().setRelation("self")
                .setUrl("http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=unknown&_count=10&_offset=0");

        when(fhirEobService.searchByPatient(eq("unknown"), anyInt(), anyInt(), anyString()))
                .thenReturn(emptyBundle);

        mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", "unknown")
                        .accept(FhirMediaType.APPLICATION_FHIR_JSON_VALUE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total", is(0)))
                .andExpect(jsonPath("$.entry").doesNotExist());
    }

    @Test
    public void paginationNextLink() throws Exception {
        Bundle bundle = new Bundle();
        bundle.setType(Bundle.BundleType.SEARCHSET);
        bundle.setTotal(5);
        bundle.addLink().setRelation("self")
                .setUrl("http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=p2&_count=2&_offset=0");
        bundle.addLink().setRelation("next")
                .setUrl("http://localhost/rest/fhir/r4/ExplanationOfBenefit?patient=p2&_count=2&_offset=2");

        ExplanationOfBenefit eob1 = new ExplanationOfBenefit();
        eob1.setId("eob-1");
        eob1.setStatus(ExplanationOfBenefit.ExplanationOfBenefitStatus.ACTIVE);
        bundle.addEntry().setResource(eob1);

        ExplanationOfBenefit eob2 = new ExplanationOfBenefit();
        eob2.setId("eob-2");
        eob2.setStatus(ExplanationOfBenefit.ExplanationOfBenefitStatus.ACTIVE);
        bundle.addEntry().setResource(eob2);

        when(fhirEobService.searchByPatient(eq("p2"), eq(2), eq(0), anyString()))
                .thenReturn(bundle);

        mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                        .param("patient", "p2")
                        .param("_count", "2")
                        .param("_offset", "0")
                        .accept(FhirMediaType.APPLICATION_FHIR_JSON_VALUE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total", is(5)))
                .andExpect(jsonPath("$.link[0].relation", is("self")))
                .andExpect(jsonPath("$.link[1].relation", is("next")))
                .andExpect(jsonPath("$.entry").isArray())
                .andExpect(jsonPath("$.entry.length()", is(2)));
    }
}

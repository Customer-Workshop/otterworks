package com.otterworks.report.fhir;

import com.otterworks.report.model.ehr.Composition;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.CodeableConcept;
import org.hl7.fhir.r4.model.Coding;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.DiagnosisComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ItemComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ProcedureComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.Use;
import org.hl7.fhir.r4.model.Reference;
import org.springframework.stereotype.Service;

import java.util.Date;
import java.util.List;

@Service
public class EobMappingService {

    private static final String ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10";
    private static final String CPT_SYSTEM = "http://www.ama-assn.org/go/cpt";
    private static final String HCPCS_SYSTEM = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets";

    public ExplanationOfBenefit mapToEob(Composition composition, String patientId) {
        ExplanationOfBenefit eob = new ExplanationOfBenefit();

        eob.setId(composition.getCompositionId().toString());
        eob.setStatus(ExplanationOfBenefit.ExplanationOfBenefitStatus.ACTIVE);
        eob.setUse(Use.CLAIM);
        eob.setType(mapEncounterType(composition.getEncounterType()));
        eob.setPatient(new Reference("Patient/" + patientId));

        Date created = composition.getStartTime() != null
                ? composition.getStartTime()
                : composition.getCommitTime();
        eob.setCreated(created);

        if (composition.getDiagnosisCode() != null) {
            String system = resolveDiagnosisSystem(composition.getDiagnosisSystem());
            DiagnosisComponent diag = new DiagnosisComponent();
            diag.setSequence(1);
            diag.setDiagnosis(new CodeableConcept()
                    .addCoding(new Coding(system,
                            composition.getDiagnosisCode(),
                            composition.getDiagnosisDisplay())));
            eob.addDiagnosis(diag);
        }

        if (composition.getProcedureCode() != null) {
            String system = resolveProcedureSystem(composition.getProcedureSystem());
            ProcedureComponent proc = new ProcedureComponent();
            proc.setSequence(1);
            proc.setProcedure(new CodeableConcept()
                    .addCoding(new Coding(system,
                            composition.getProcedureCode(),
                            composition.getProcedureDisplay())));
            eob.addProcedure(proc);

            ItemComponent item = new ItemComponent();
            item.setSequence(1);
            item.setProductOrService(new CodeableConcept()
                    .addCoding(new Coding(system,
                            composition.getProcedureCode(),
                            composition.getProcedureDisplay())));
            eob.addItem(item);
        }

        if (composition.getProviderName() != null) {
            eob.setProvider(new Reference().setDisplay(composition.getProviderName()));
        }

        if (composition.getFacilityName() != null) {
            eob.setFacility(new Reference().setDisplay(composition.getFacilityName()));
        }

        return eob;
    }

    public Bundle buildSearchBundle(List<ExplanationOfBenefit> eobs, long total,
                                    String selfUrl, String nextUrl) {
        Bundle bundle = new Bundle();
        bundle.setType(Bundle.BundleType.SEARCHSET);
        bundle.setTotal((int) total);

        bundle.addLink().setRelation("self").setUrl(selfUrl);
        if (nextUrl != null) {
            bundle.addLink().setRelation("next").setUrl(nextUrl);
        }

        for (ExplanationOfBenefit eob : eobs) {
            Bundle.BundleEntryComponent entry = bundle.addEntry();
            entry.setResource(eob);
            entry.setFullUrl("ExplanationOfBenefit/" + eob.getId());
        }

        return bundle;
    }

    private CodeableConcept mapEncounterType(String encounterType) {
        if (encounterType == null) {
            return new CodeableConcept()
                    .addCoding(new Coding(
                            "http://terminology.hl7.org/CodeSystem/claim-type",
                            "institutional", "Institutional"));
        }

        String code;
        String display;
        switch (encounterType.toLowerCase()) {
            case "pharmacy":
                code = "pharmacy";
                display = "Pharmacy";
                break;
            case "professional":
            case "outpatient":
                code = "professional";
                display = "Professional";
                break;
            case "institutional":
            case "inpatient":
            default:
                code = "institutional";
                display = "Institutional";
                break;
        }
        return new CodeableConcept()
                .addCoding(new Coding(
                        "http://terminology.hl7.org/CodeSystem/claim-type",
                        code, display));
    }

    private String resolveDiagnosisSystem(String system) {
        if (system != null && !system.isEmpty()) {
            return system;
        }
        return ICD10_SYSTEM;
    }

    private String resolveProcedureSystem(String system) {
        if (system != null && !system.isEmpty()) {
            return system;
        }
        return CPT_SYSTEM;
    }
}

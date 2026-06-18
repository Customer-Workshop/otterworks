package org.ehrbase.service.fhir;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import org.ehrbase.model.Composition;
import org.ehrbase.model.DvCodedText;
import org.ehrbase.service.validation.BillingCategory;
import org.hl7.fhir.r4.model.CodeableConcept;
import org.hl7.fhir.r4.model.Coding;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.DiagnosisComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ExplanationOfBenefitStatus;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ItemComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ProcedureComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.Use;
import org.hl7.fhir.r4.model.Reference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Maps openEHR {@link Composition} data containing billing codes to FHIR R4
 * {@link ExplanationOfBenefit} resources. Classifies {@link DvCodedText} items
 * by their terminology system URI into diagnosis, procedure, and line-item
 * categories.
 */
@Service
public class EobMappingService {

    private static final Logger log = LoggerFactory.getLogger(EobMappingService.class);

    private static final String ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm";
    private static final String CPT_SYSTEM = "http://www.ama-assn.org/go/cpt";
    private static final String HCPCS_SYSTEM = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets";
    private static final String SNOMED_SYSTEM = "http://snomed.info/sct";

    private static final String EOB_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/claim-type";

    /**
     * Maps a single openEHR composition to a FHIR ExplanationOfBenefit resource.
     *
     * @param composition the source composition containing billing codes
     * @param ehrId       the EHR identifier owning the composition
     * @param patientId   the patient reference identifier
     * @return the mapped EOB resource
     */
    public ExplanationOfBenefit mapToEob(Composition composition, UUID ehrId, String patientId) {
        ExplanationOfBenefit eob = new ExplanationOfBenefit();

        eob.setId(composition.uid().toString());
        eob.setStatus(ExplanationOfBenefitStatus.ACTIVE);
        eob.setType(buildClaimType());
        eob.setUse(Use.CLAIM);
        eob.setPatient(new Reference("Patient/" + patientId));
        eob.setCreated(new Date());
        eob.setProvider(new Reference("Organization/" + ehrId));
        eob.setFacility(new Reference("Location/" + ehrId));

        List<DvCodedText> codedTexts = composition.codedTexts();
        int diagnosisSequence = 1;
        int procedureSequence = 1;
        int itemSequence = 1;

        List<DiagnosisComponent> diagnoses = new ArrayList<>();
        List<ProcedureComponent> procedures = new ArrayList<>();
        List<ItemComponent> items = new ArrayList<>();

        for (DvCodedText codedText : codedTexts) {
            BillingCategory category = classifyCode(codedText.system());
            if (category == null) {
                continue;
            }

            switch (category) {
                case DIAGNOSIS -> {
                    DiagnosisComponent diag = new DiagnosisComponent();
                    diag.setSequence(diagnosisSequence++);
                    diag.setDiagnosis(buildCodeableConcept(codedText));
                    diagnoses.add(diag);
                }
                case PROCEDURE -> {
                    ProcedureComponent proc = new ProcedureComponent();
                    proc.setSequence(procedureSequence++);
                    proc.setProcedure(buildCodeableConcept(codedText));
                    procedures.add(proc);

                    ItemComponent item = new ItemComponent();
                    item.setSequence(itemSequence++);
                    item.setProductOrService(buildCodeableConcept(codedText));
                    items.add(item);
                }
                case CLINICAL_JUSTIFICATION -> {
                    ItemComponent item = new ItemComponent();
                    item.setSequence(itemSequence++);
                    item.setProductOrService(buildCodeableConcept(codedText));
                    items.add(item);
                }
            }
        }

        eob.setDiagnosis(diagnoses);
        eob.setProcedure(procedures);
        eob.setItem(items);

        log.debug("Mapped composition {} to EOB with {} diagnoses, {} procedures, {} items",
                composition.uid(), diagnoses.size(), procedures.size(), items.size());

        return eob;
    }

    /**
     * Classifies a terminology system URI into a billing category.
     *
     * @param system the terminology system URI
     * @return the billing category, or null if not a billing system
     */
    BillingCategory classifyCode(String system) {
        if (system == null) {
            return null;
        }
        return switch (system) {
            case ICD10_SYSTEM -> BillingCategory.DIAGNOSIS;
            case CPT_SYSTEM, HCPCS_SYSTEM -> BillingCategory.PROCEDURE;
            case SNOMED_SYSTEM -> BillingCategory.CLINICAL_JUSTIFICATION;
            default -> null;
        };
    }

    private CodeableConcept buildClaimType() {
        CodeableConcept type = new CodeableConcept();
        type.addCoding(new Coding()
                .setSystem(EOB_TYPE_SYSTEM)
                .setCode("professional")
                .setDisplay("Professional"));
        return type;
    }

    private CodeableConcept buildCodeableConcept(DvCodedText codedText) {
        CodeableConcept concept = new CodeableConcept();
        Coding coding = new Coding()
                .setSystem(codedText.system())
                .setCode(codedText.code());
        if (codedText.value() != null && !codedText.value().isBlank()) {
            coding.setDisplay(codedText.value());
        }
        concept.addCoding(coding);
        return concept;
    }
}

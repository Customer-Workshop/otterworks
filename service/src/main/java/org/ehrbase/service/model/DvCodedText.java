package org.ehrbase.service.model;

import java.util.Objects;

/**
 * Represents a coded text value, analogous to openEHR DV_CODED_TEXT.
 */
public record DvCodedText(String value, CodePhrase definingCode) {

    public DvCodedText {
        Objects.requireNonNull(value, "value must not be null");
        Objects.requireNonNull(definingCode, "definingCode must not be null");
    }

    public String codeSystem() {
        return definingCode.terminologyId();
    }

    public String code() {
        return definingCode.codeString();
    }
}

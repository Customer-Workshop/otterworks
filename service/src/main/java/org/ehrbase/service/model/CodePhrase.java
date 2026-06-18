package org.ehrbase.service.model;

import java.util.Objects;

/**
 * Represents a coded value with its terminology system, analogous to openEHR CODE_PHRASE.
 */
public record CodePhrase(String terminologyId, String codeString) {

    public CodePhrase {
        Objects.requireNonNull(terminologyId, "terminologyId must not be null");
        Objects.requireNonNull(codeString, "codeString must not be null");
    }
}

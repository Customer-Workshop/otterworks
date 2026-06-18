package org.ehrbase.model;

/**
 * Simplified openEHR DV_CODED_TEXT representation carrying a terminology
 * system URI, code string, display value, and the archetype path within
 * the enclosing Composition.
 */
public record DvCodedText(
        String system,
        String code,
        String value,
        String path
) {

    public DvCodedText {
        if (system == null || system.isBlank()) {
            throw new IllegalArgumentException("system must not be blank");
        }
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code must not be blank");
        }
    }
}

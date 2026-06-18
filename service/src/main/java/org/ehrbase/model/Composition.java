package org.ehrbase.model;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * Simplified openEHR COMPOSITION representation. Carries an identifier
 * and a flat collection of {@link DvCodedText} items extracted from
 * the composition's archetype tree.
 */
public final class Composition {

    private final UUID uid;
    private final List<DvCodedText> codedTexts;

    public Composition(UUID uid, List<DvCodedText> codedTexts) {
        this.uid = uid;
        this.codedTexts = codedTexts == null
                ? List.of()
                : Collections.unmodifiableList(new ArrayList<>(codedTexts));
    }

    public UUID uid() {
        return uid;
    }

    public List<DvCodedText> codedTexts() {
        return codedTexts;
    }
}

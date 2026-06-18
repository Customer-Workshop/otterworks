package org.ehrbase.service.model;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Simplified representation of an openEHR Composition for validation purposes.
 */
public class Composition {

    private UUID uid;

    private String archetypeNodeId;

    private final List<CompositionEntry> entries = new ArrayList<>();

    public Composition() {}

    public Composition(UUID uid, String archetypeNodeId) {
        this.uid = uid;
        this.archetypeNodeId = archetypeNodeId;
    }

    public UUID getUid() {
        return uid;
    }

    public void setUid(UUID uid) {
        this.uid = uid;
    }

    public String getArchetypeNodeId() {
        return archetypeNodeId;
    }

    public void setArchetypeNodeId(String archetypeNodeId) {
        this.archetypeNodeId = archetypeNodeId;
    }

    public List<CompositionEntry> getEntries() {
        return entries;
    }

    public void addEntry(CompositionEntry entry) {
        entries.add(entry);
    }

    public static class CompositionEntry {

        private String path;

        private DvCodedText codedText;

        public CompositionEntry() {}

        public CompositionEntry(String path, DvCodedText codedText) {
            this.path = path;
            this.codedText = codedText;
        }

        public String getPath() {
            return path;
        }

        public void setPath(String path) {
            this.path = path;
        }

        public DvCodedText getCodedText() {
            return codedText;
        }

        public void setCodedText(DvCodedText codedText) {
            this.codedText = codedText;
        }
    }
}

package com.boxoffice.confirmations.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class RefsTest {

    @Test
    void ticketCodesUseMonolithPrefixAlphabetAndLength() {
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 500; i++) {
            String code = Refs.next("TK");
            assertThat(code).matches("^TK-[" + Refs.ALPHABET + "]{10}$");
            seen.add(code);
        }
        assertThat(seen).hasSize(500);
    }

    @Test
    void alphabetExcludesAmbiguousGlyphs() {
        assertThat(Refs.ALPHABET).doesNotContain("0", "1", "I", "O").hasSize(32);
    }
}

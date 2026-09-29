package com.boxoffice.common;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class RefsTest {

    @Test
    void refsArePrefixedAndUnambiguous() {
        String ref = Refs.next("BO");
        assertTrue(ref.matches("BO-[A-HJ-NP-Z2-9]{10}"), ref);
        assertNotEquals(ref, Refs.next("BO"));
    }
}

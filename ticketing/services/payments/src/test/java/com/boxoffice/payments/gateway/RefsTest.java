package com.boxoffice.payments.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class RefsTest {

    @Test
    void refsHaveMonolithShapeAndAreUnique() {
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 1000; i++) {
            String ref = Refs.next("GW");
            assertThat(ref).matches("GW-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{10}");
            assertThat(seen.add(ref)).isTrue();
        }
    }
}

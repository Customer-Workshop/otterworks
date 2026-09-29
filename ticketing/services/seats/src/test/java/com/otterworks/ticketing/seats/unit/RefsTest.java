package com.otterworks.ticketing.seats.unit;

import static org.assertj.core.api.Assertions.assertThat;

import com.otterworks.ticketing.seats.config.Refs;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class RefsTest {

    @Test
    void holdRefHasMonolithShape() {
        String ref = Refs.next("H");
        assertThat(ref).matches("H-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{10}");
    }

    @Test
    void refsAreUnique() {
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 5000; i++) {
            assertThat(seen.add(Refs.next("H"))).isTrue();
        }
    }
}

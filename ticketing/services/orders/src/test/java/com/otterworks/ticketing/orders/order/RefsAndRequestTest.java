package com.otterworks.ticketing.orders.order;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class RefsAndRequestTest {

    @Test
    void refsUseTheLegacyPrefixAndAlphabet() {
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 200; i++) {
            String ref = Refs.next("BO");
            assertThat(ref).matches("BO-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{10}");
            seen.add(ref);
        }
        assertThat(seen).hasSize(200);
    }

    @Test
    void legacyDefaultsApply() {
        PlaceOrderRequest req = new PlaceOrderRequest(1L, null, " Kiosk+1@Example.Test ", 2, null, null, null, null, "  ", "API");
        assertThat(req.normalisedEmail()).isEqualTo("kiosk+1@example.test");
        assertThat(req.deliveryOrDefault()).isEqualTo("MOBILE");
        assertThat(req.cardLast4OrDefault()).isEqualTo("4242");
        assertThat(req.clientRefOrNull()).isNull();
        PlaceOrderRequest explicit = new PlaceOrderRequest(1L, null, "a@example.test", 1, null, null, "PRINT", "0000", " k6-1 ", "API");
        assertThat(explicit.deliveryOrDefault()).isEqualTo("PRINT");
        assertThat(explicit.cardLast4OrDefault()).isEqualTo("0000");
        assertThat(explicit.clientRefOrNull()).isEqualTo("k6-1");
    }
}

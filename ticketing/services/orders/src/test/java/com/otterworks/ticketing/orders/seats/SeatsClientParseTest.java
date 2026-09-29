package com.otterworks.ticketing.orders.seats;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

class SeatsClientParseTest {

    private final ObjectMapper json = new ObjectMapper();
    private final SeatsClient client = new SeatsClient(RestClient.create("http://seats.test"), json);

    @Test
    void parsesTheHoldContract() throws Exception {
        SeatsClient.Hold hold = client.parseHold(json.readTree("""
                {"holdRef":"HD-ABC","performanceId":7,"expiresAt":"2026-01-01T00:10:00Z",
                 "seats":[{"seatInventoryId":11,"section":"T1","rowLabel":"R01","seatNumber":3,
                           "priceZoneId":7,"zoneCode":"P1","zoneName":"Premium"}],
                 "zoneTally":[{"priceZoneId":7,"notAvailable":1,"total":240}]}"""));
        assertThat(hold.holdRef()).isEqualTo("HD-ABC");
        assertThat(hold.performanceId()).isEqualTo(7L);
        assertThat(hold.active()).isTrue();
        assertThat(hold.expiresAt()).isEqualTo("2026-01-01T00:10:00Z");
        assertThat(hold.seats()).singleElement().satisfies(s -> {
            assertThat(s.seatInventoryId()).isEqualTo(11);
            assertThat(s.priceZoneId()).isEqualTo(7);
            assertThat(s.section()).isEqualTo("T1");
            assertThat(s.seatNumber()).isEqualTo(3);
        });
        assertThat(hold.zoneTally()).singleElement().satisfies(t -> assertThat(t.total()).isEqualTo(240));
    }

    @Test
    void holdStatusUsesActiveFlagOrStatus() throws Exception {
        assertThat(client.parseHold(json.readTree("{\"holdRef\":\"H\",\"status\":\"EXPIRED\"}")).active()).isFalse();
        assertThat(client.parseHold(json.readTree("{\"holdRef\":\"H\",\"status\":\"ACTIVE\",\"active\":false}")).active()).isFalse();
        assertThat(client.parseHold(json.readTree("{\"holdRef\":\"H\",\"status\":\"ACTIVE\"}")).active()).isTrue();
        assertThat(client.parseHold(json.readTree("{\"holdRef\":\"H\"}")).performanceId()).isNull();
    }
}

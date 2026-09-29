package com.boxoffice.confirmations.events;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

import com.boxoffice.confirmations.config.ConfirmationsProperties;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InboxDeliveryTest {

    private static final String ORDERS = "http://tkt01-orders.tkt01-after.svc.cluster.local/events/order-confirmed";
    private static final String SEATS = "http://tkt01-seats.tkt01-after.svc.cluster.local/events/order-confirmed";

    private MockRestServiceServer server;
    private InboxDelivery delivery;
    private SimpleMeterRegistry registry;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        registry = new SimpleMeterRegistry();
        delivery = new InboxDelivery(builder.build(),
                new ConfirmationsProperties("tkt01", false, "tkt01-order-confirmed", ORDERS, SEATS, 1000, 1000), registry);
    }

    private static OrderConfirmedEvent event() {
        return new OrderConfirmedEvent("BO-A", "HD-1", 7L, 1,
                List.of(new OrderConfirmedEvent.Ticket("TK-AAAAAAAAAA", 120006L, "bc-120006")),
                "fan@example.test", "2026-09-29T01:22:50.500Z");
    }

    @Test
    void postsTheSamePayloadToOrdersThenSeats() {
        for (String url : List.of(ORDERS, SEATS)) {
            server.expect(once(), requestTo(url)).andExpect(method(HttpMethod.POST))
                    .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                    .andExpect(jsonPath("$.orderRef").value("BO-A"))
                    .andExpect(jsonPath("$.ticketCount").value(1))
                    .andExpect(jsonPath("$.tickets[0].seatInventoryId").value(120006))
                    .andRespond(withStatus(HttpStatus.ACCEPTED));
        }

        Map<String, Integer> statuses = delivery.deliver(event());

        server.verify();
        assertThat(statuses).containsExactly(Map.entry("orders", 202), Map.entry("seats", 202));
    }

    @Test
    void stillTriesSeatsWhenOrdersRejectsThenRaisesTheFirstFailure() {
        server.expect(once(), requestTo(ORDERS)).andRespond(withServerError());
        server.expect(once(), requestTo(SEATS)).andRespond(withStatus(HttpStatus.OK));

        assertThatThrownBy(() -> delivery.deliver(event()))
                .isInstanceOf(DeliveryException.class)
                .satisfies(e -> assertThat(((DeliveryException) e).target()).isEqualTo("orders"))
                .hasMessageContaining("HTTP 500");
        server.verify();
        assertThat(registry.counter("confirmations_inbox_deliveries_total", "target", "orders", "outcome", "rejected").count()).isEqualTo(1.0);
        assertThat(registry.counter("confirmations_inbox_deliveries_total", "target", "seats", "outcome", "ok").count()).isEqualTo(1.0);
    }
}

package com.boxoffice.confirmations.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.boxoffice.confirmations.events.LoggingOrderConfirmedPublisher;
import com.boxoffice.confirmations.events.OrderConfirmedEvent;
import com.boxoffice.confirmations.events.OrderConfirmedPublisher;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * Replays the monolith interactions recorded in {@code src/test/resources/contracts} against this service and
 * asserts the same outcomes: ticket count and seats per order, the confirmation e-mail as ConfirmationBean wrote it,
 * the 404 envelope, and the stats deltas the before state showed for the same purchases.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(InboxStubConfig.class)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class ConfirmationsContractTest {

    private static final String ORDERS = "http://tkt01-orders.tkt01-after.svc.cluster.local/events/order-confirmed";
    private static final String SEATS = "http://tkt01-seats.tkt01-after.svc.cluster.local/events/order-confirmed";
    private static final List<String> CONFIRM_CASES = List.of("confirm-1-ticket", "confirm-2-tickets", "confirm-3-tickets");

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired MockRestServiceServer inboxServer;
    @Autowired OrderConfirmedPublisher publisher;

    private LoggingOrderConfirmedPublisher.InMemory records() {
        return (LoggingOrderConfirmedPublisher.InMemory) publisher;
    }

    @BeforeEach
    void resetOutbound() {
        inboxServer.reset();
        records().clear();
    }

    private void expectInboxes(String orderRef, int ticketCount) {
        for (String url : List.of(ORDERS, SEATS)) {
            inboxServer.expect(once(), requestTo(url)).andExpect(method(HttpMethod.POST))
                    .andExpect(jsonPath("$.orderRef").value(orderRef))
                    .andExpect(jsonPath("$.ticketCount").value(ticketCount))
                    .andRespond(withSuccess());
        }
    }

    private JsonNode postCaptured(JsonNode fixture, int expectedStatus) throws Exception {
        MvcResult r = mvc.perform(post("/events/payment-captured").contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsString(fixture.get("paymentCaptured"))))
                .andExpect(status().is(expectedStatus)).andReturn();
        return json.readTree(r.getResponse().getContentAsString());
    }

    private JsonNode getConfirmation(String orderRef, int expectedStatus) throws Exception {
        MvcResult r = mvc.perform(get("/api/confirmations/{ref}", orderRef)).andExpect(status().is(expectedStatus)).andReturn();
        return json.readTree(r.getResponse().getContentAsString());
    }

    private JsonNode stats() throws Exception {
        return json.readTree(mvc.perform(get("/stats")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
    }

    private static List<Long> longs(JsonNode array, String field) {
        List<Long> out = new ArrayList<>();
        array.forEach(n -> out.add(field == null ? n.asLong() : n.get(field).asLong()));
        return out;
    }

    @Test
    @Order(1)
    void statsStartAtTheBeforeStateBaseline() throws Exception {
        JsonNode s = stats();
        assertThat(s.get("ticketsIssued").asLong()).isZero();
        assertThat(s.get("confirmationsQueued").asLong()).isZero();
        assertThat(s.get("confirmationsSent").asLong()).isZero();
    }

    @Order(2)
    @ParameterizedTest(name = "{0}")
    @ValueSource(strings = {"confirm-1-ticket", "confirm-2-tickets", "confirm-3-tickets"})
    void paymentCapturedIssuesTheMonolithsTicketsAndConfirmation(String name) throws Exception {
        JsonNode fx = ContractFixture.load(name);
        JsonNode expected = fx.get("expected");
        JsonNode monolith = fx.get("monolith").get("purchaseResponse");
        String orderRef = fx.get("paymentCaptured").get("orderRef").asText();
        int ticketCount = expected.get("ticketCount").asInt();
        assertThat(ticketCount).as("fixture agrees with the monolith purchase response").isEqualTo(monolith.get("tickets").asInt());
        assertThat(monolith.get("status").asText()).isEqualTo("CONFIRMED");
        expectInboxes(orderRef, ticketCount);

        JsonNode res = postCaptured(fx, 201);

        assertThat(res.get("status").asText()).isEqualTo("CONFIRMED");
        assertThat(res.get("replay").asBoolean()).isFalse();
        assertThat(res.get("ticketCount").asInt()).isEqualTo(ticketCount);
        assertThat(longs(res.get("tickets"), "seatInventoryId")).containsExactlyElementsOf(longs(expected.get("seatInventoryIds"), null));
        String pattern = expected.get("ticketCodePattern").asText();
        Set<String> codes = new HashSet<>();
        res.get("tickets").forEach(t -> {
            assertThat(t.get("ticketCode").asText()).matches(pattern);
            assertThat(t.get("barcode").asText()).isNotBlank();
            assertThat(t.get("issuedAt").asText()).isNotBlank();
            codes.add(t.get("ticketCode").asText());
        });
        assertThat(codes).hasSize(ticketCount);
        assertThat(res.get("publishedTo").asText()).isEqualTo("tkt01-order-confirmed");
        assertThat(res.get("delivered").get("orders").asInt()).isEqualTo(200);
        assertThat(res.get("delivered").get("seats").asInt()).isEqualTo(200);

        JsonNode view = getConfirmation(orderRef, 200);
        JsonNode exConf = expected.get("confirmation");
        assertThat(view.get("ticketCount").asInt()).isEqualTo(ticketCount);
        assertThat(view.get("confirmation").get("recipient").asText()).isEqualTo(exConf.get("recipient").asText());
        assertThat(view.get("confirmation").get("subject").asText()).isEqualTo(exConf.get("subject").asText());
        assertThat(view.get("confirmation").get("body").asText()).isEqualTo(exConf.get("body").asText());
        assertThat(view.get("confirmation").get("status").asText()).isEqualTo(exConf.get("status").asText());
        assertThat(view.get("confirmation").get("sentAt").isNull()).isTrue();

        JsonNode exEvent = expected.get("orderConfirmed");
        assertThat(records().records()).singleElement().satisfies(e -> {
            assertThat(e.orderRef()).isEqualTo(exEvent.get("orderRef").asText());
            assertThat(e.holdRef()).isEqualTo(exEvent.get("holdRef").asText());
            assertThat(e.performanceId()).isEqualTo(exEvent.get("performanceId").asLong());
            assertThat(e.ticketCount()).isEqualTo(exEvent.get("ticketCount").asInt());
            assertThat(e.recipient()).isEqualTo(exEvent.get("recipient").asText());
            assertThat(e.tickets()).extracting(OrderConfirmedEvent.Ticket::ticketCode).containsExactlyInAnyOrderElementsOf(codes);
        });
        inboxServer.verify();
    }

    @Test
    @Order(3)
    void replayReturnsTheSameTicketsAndRedeliversWithoutDuplicates() throws Exception {
        JsonNode fx = ContractFixture.load("confirm-2-tickets");
        String orderRef = fx.get("paymentCaptured").get("orderRef").asText();
        List<String> before = jdbc.queryForList("SELECT ticket_code FROM tickets WHERE order_ref = ? ORDER BY id", String.class, orderRef);
        assertThat(before).hasSize(2);
        expectInboxes(orderRef, 2);

        JsonNode res = postCaptured(fx, 200);

        assertThat(res.get("replay").asBoolean()).isTrue();
        List<String> codes = new ArrayList<>();
        res.get("tickets").forEach(t -> codes.add(t.get("ticketCode").asText()));
        assertThat(codes).containsExactlyElementsOf(before);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM tickets WHERE order_ref = ?", Long.class, orderRef)).isEqualTo(2L);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM confirmations WHERE order_ref = ?", Long.class, orderRef)).isEqualTo(1L);
        assertThat(records().records()).singleElement().satisfies(e -> assertThat(e.orderRef()).isEqualTo(orderRef));
        inboxServer.verify();
    }

    @Test
    @Order(4)
    void inboxOutageLeavesTicketsCommittedAndAnswers502UntilTheRetrySucceeds() throws Exception {
        JsonNode fx = json.readTree(json.writeValueAsString(ContractFixture.load("confirm-1-ticket")));
        String orderRef = "BO-RETRY000001";
        ((com.fasterxml.jackson.databind.node.ObjectNode) fx.get("paymentCaptured")).put("orderRef", orderRef);
        ((com.fasterxml.jackson.databind.node.ObjectNode) fx.get("paymentCaptured").get("order").get("items").get(0)).put("seatInventoryId", 13);
        inboxServer.expect(once(), requestTo(ORDERS)).andRespond(withSuccess());
        inboxServer.expect(once(), requestTo(SEATS)).andRespond(withServerError());

        JsonNode failed = postCaptured(fx, 502);

        assertThat(failed.get("error").asText()).isEqualTo("DELIVERY_FAILED");
        assertThat(failed.get("target").asText()).isEqualTo("seats");
        assertThat(failed.get("retryable").asBoolean()).isTrue();
        List<String> issued = jdbc.queryForList("SELECT ticket_code FROM tickets WHERE order_ref = ?", String.class, orderRef);
        assertThat(issued).hasSize(1);
        inboxServer.verify();

        inboxServer.reset();
        records().clear();
        expectInboxes(orderRef, 1);
        JsonNode retried = postCaptured(fx, 200);
        assertThat(retried.get("replay").asBoolean()).isTrue();
        assertThat(retried.get("tickets").get(0).get("ticketCode").asText()).isEqualTo(issued.get(0));
        inboxServer.verify();
        jdbc.update("DELETE FROM tickets WHERE order_ref = ?", orderRef);
        jdbc.update("DELETE FROM confirmations WHERE order_ref = ?", orderRef);
    }

    @Test
    @Order(5)
    void unknownOrderRefAnswersTheMonolithsNotFoundEnvelope() throws Exception {
        JsonNode fx = ContractFixture.load("order-not-found");
        JsonNode expected = fx.get("expected");
        assertThat(expected.get("status").asInt()).isEqualTo(fx.get("monolith").get("status").asInt());

        String ref = expected.get("path").asText().substring("/api/confirmations/".length());
        JsonNode body = getConfirmation(ref, expected.get("status").asInt());

        assertThat(body.get("error").asText()).isEqualTo(expected.get("body").get("error").asText());
        assertThat(body.get("message").asText()).isEqualTo(expected.get("body").get("message").asText());
    }

    @Test
    @Order(6)
    void statsDeltaMatchesTheBeforeStateForTheSamePurchases() throws Exception {
        JsonNode fx = ContractFixture.load("stats-delta");
        JsonNode m = fx.get("monolith");
        JsonNode expected = fx.get("expected");
        assertThat(expected.get("ticketsIssuedDelta").asLong())
                .isEqualTo(m.get("after").get("ticketsIssued").asLong() - m.get("before").get("ticketsIssued").asLong());
        assertThat(expected.get("confirmationsQueuedDelta").asLong())
                .isEqualTo(m.get("after").get("confirmationsQueued").asLong() - m.get("before").get("confirmationsQueued").asLong());

        JsonNode s = stats();

        assertThat(s.get("ticketsIssued").asLong()).isEqualTo(expected.get("ticketsIssuedDelta").asLong());
        assertThat(s.get("confirmationsQueued").asLong()).isEqualTo(expected.get("confirmationsQueuedDelta").asLong());
        assertThat(s.get("confirmationsSent").asLong()).isEqualTo(expected.get("confirmationsSentDelta").asLong());
        assertThat(s.get("ordersConfirmed").asLong()).isEqualTo(CONFIRM_CASES.size());
    }

    @Test
    @Order(7)
    void actuatorHealthAndPrometheusAreExposed() throws Exception {
        mvc.perform(get("/actuator/health/readiness")).andExpect(status().isOk());
        mvc.perform(get("/actuator/health/liveness")).andExpect(status().isOk());
        String metrics = mvc.perform(get("/actuator/prometheus")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertThat(metrics).contains("confirmations_tickets_issued_total").contains("run_token=\"tkt01\"");
    }

    @Test
    @Order(8)
    void malformedInboxPayloadIsRejectedWithoutIssuingTickets() throws Exception {
        long before = jdbc.queryForObject("SELECT COUNT(*) FROM tickets", Long.class);
        mvc.perform(post("/events/payment-captured").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"orderRef\":\"BO-BAD\",\"order\":{\"customerEmail\":\"x@example.test\",\"items\":[]}}"))
                .andExpect(status().isBadRequest());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM tickets", Long.class)).isEqualTo(before);
    }
}

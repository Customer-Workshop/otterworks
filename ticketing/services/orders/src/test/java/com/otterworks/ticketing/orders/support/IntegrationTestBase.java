package com.otterworks.ticketing.orders.support;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.MockServerRestClientCustomizer;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.match.MockRestRequestMatchers;
import org.springframework.test.web.client.response.MockRestResponseCreators;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

@SpringBootTest
@AutoConfigureMockMvc
@Import(SeatsStubConfig.class)
@ContextConfiguration(initializers = EmbeddedPostgresInitializer.class)
@TestPropertySource(properties = {
        "orders.token=test",
        "orders.seats.base-url=http://seats.test",
        "spring.kafka.bootstrap-servers=localhost:1"
})
public abstract class IntegrationTestBase {

    @Autowired
    protected MockMvc mvc;
    @Autowired
    protected ObjectMapper json;
    @Autowired
    protected JdbcClient jdbc;
    @Autowired
    private MockServerRestClientCustomizer seatsCustomizer;

    protected MockRestServiceServer seats;
    protected SeatsStub seatsStub;

    @BeforeEach
    void resetSeats() {
        seats = seatsCustomizer.getServer();
        seats.reset();
        seatsStub = new SeatsStub(jdbc);
    }

    @AfterEach
    void verifySeats() {
        seats.verify();
    }

    /** MockRestServiceServer rejects new expectations once requests were made: verify and start a new round. */
    protected void nextSeatsRound() {
        seats.verify();
        seats.reset();
    }

    protected void stubHold(Map<String, Object> hold) throws Exception {
        seats.expect(MockRestRequestMatchers.requestTo("http://seats.test/api/holds"))
                .andExpect(MockRestRequestMatchers.method(HttpMethod.POST))
                .andRespond(MockRestResponseCreators.withStatus(HttpStatus.CREATED)
                        .contentType(MediaType.APPLICATION_JSON).body(json.writeValueAsString(hold)));
    }

    protected void stubHoldError(int status, String error, String message) throws Exception {
        seats.expect(MockRestRequestMatchers.requestTo("http://seats.test/api/holds"))
                .andExpect(MockRestRequestMatchers.method(HttpMethod.POST))
                .andRespond(MockRestResponseCreators.withStatus(HttpStatus.valueOf(status))
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(json.writeValueAsString(Map.of("error", error, "message", message))));
    }

    protected void stubHoldLookup(String holdRef, Map<String, Object> hold) throws Exception {
        seats.expect(MockRestRequestMatchers.requestTo("http://seats.test/api/holds/" + holdRef))
                .andExpect(MockRestRequestMatchers.method(HttpMethod.GET))
                .andRespond(MockRestResponseCreators.withStatus(HttpStatus.OK)
                        .contentType(MediaType.APPLICATION_JSON).body(json.writeValueAsString(hold)));
    }

    protected Response post(String path, Object body) throws Exception {
        String raw = body instanceof String s ? s : json.writeValueAsString(body);
        MvcResult r = mvc.perform(MockMvcRequestBuilders.post(path).contentType(MediaType.APPLICATION_JSON).content(raw))
                .andReturn();
        return new Response(r.getResponse().getStatus(), json.readTree(r.getResponse().getContentAsString()));
    }

    protected Response get(String path) throws Exception {
        MvcResult r = mvc.perform(MockMvcRequestBuilders.get(path)).andReturn();
        String content = r.getResponse().getContentAsString();
        return new Response(r.getResponse().getStatus(), content.isEmpty() ? json.nullNode() : json.readTree(content));
    }

    public record Response(int status, JsonNode body) {
    }
}

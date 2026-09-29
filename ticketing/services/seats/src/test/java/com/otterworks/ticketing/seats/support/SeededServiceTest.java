package com.otterworks.ticketing.seats.support;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * Boots the service against the seeded embedded database (V1 schema + V2 seed = the monolith's
 * synthetic seed) and returns it to the pristine seed before every test.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@AutoConfigureObservability
@Import(EmbeddedPostgresConfig.class)
public abstract class SeededServiceTest {

    @Autowired
    protected TestRestTemplate http;
    @Autowired
    protected JdbcTemplate jdbc;
    @Autowired
    protected ObjectMapper json;

    @BeforeEach
    void resetToSeed() {
        jdbc.update("UPDATE seat_inventory SET status = 'AVAILABLE', hold_id = NULL, order_ref = NULL WHERE status <> 'AVAILABLE' OR hold_id IS NOT NULL OR order_ref IS NOT NULL");
        jdbc.execute("TRUNCATE seat_hold_items, hold_expired_events, seat_holds, inbox");
    }

    protected ResponseEntity<JsonNode> get(String path) {
        return http.exchange(path, HttpMethod.GET, HttpEntity.EMPTY, JsonNode.class);
    }

    protected ResponseEntity<JsonNode> post(String path, Object body) {
        HttpHeaders h = new HttpHeaders();
        h.setContentType(MediaType.APPLICATION_JSON);
        return http.exchange(path, HttpMethod.POST, new HttpEntity<>(body, h), JsonNode.class);
    }

    protected ResponseEntity<String> postRaw(String path, String body) {
        HttpHeaders h = new HttpHeaders();
        h.setContentType(MediaType.APPLICATION_JSON);
        return http.exchange(path, HttpMethod.POST, new HttpEntity<>(body, h), String.class);
    }

    /** A recorded monolith exchange from src/test/resources/contracts. */
    protected JsonNode contract(String name) {
        try (InputStream in = getClass().getResourceAsStream("/contracts/" + name + ".json")) {
            if (in == null) {
                throw new IllegalArgumentException("no contract fixture " + name);
            }
            return json.readTree(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    protected Map<String, Object> hold(long performanceId, int quantity, String section) {
        Map<String, Object> req = new java.util.LinkedHashMap<>();
        req.put("performanceId", performanceId);
        req.put("quantity", quantity);
        if (section != null) {
            req.put("section", section);
        }
        return req;
    }
}

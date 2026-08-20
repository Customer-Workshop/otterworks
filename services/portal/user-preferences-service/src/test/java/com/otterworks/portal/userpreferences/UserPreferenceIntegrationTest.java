package com.otterworks.portal.userpreferences;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * End-to-end against PostgreSQL 16 with the real Flyway migration: the wire contract, both
 * error envelopes and the persistence side of the fabricated-defaults clause.
 */
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserPreferenceIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16");

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Autowired private TestRestTemplate rest;
    @Autowired private JdbcTemplate jdbc;

    @BeforeEach
    void emptyTable() {
        jdbc.update("DELETE FROM user_preference");
    }

    private ResponseEntity<String> put(String userId, String body) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange(
                "/api/preferences/" + userId,
                HttpMethod.PUT,
                new HttpEntity<>(body, headers),
                String.class);
    }

    private long rowCount() {
        return jdbc.queryForObject("SELECT count(*) FROM user_preference", Long.class);
    }

    /** §4: Flyway owns the schema; the natural key is the only index. */
    @Test
    void migrationCreatesTheContractSchemaWithNoExtraIndex() {
        assertThat(
                        jdbc.queryForList(
                                "SELECT column_name || ' ' || data_type || '('"
                                        + " || coalesce(character_maximum_length::text, '-') || ')'"
                                        + " || ' ' || is_nullable"
                                        + " FROM information_schema.columns"
                                        + " WHERE table_name = 'user_preference'"
                                        + " ORDER BY ordinal_position",
                                String.class))
                .containsExactly(
                        "user_id character varying(100) NO",
                        "theme character varying(20) NO",
                        "locale character varying(20) NO",
                        "email_notifications boolean(-) NO");
        assertThat(
                        jdbc.queryForList(
                                "SELECT indexname FROM pg_indexes WHERE tablename ="
                                        + " 'user_preference'",
                                String.class))
                .hasSize(1);
    }

    /** §2.1: GET never 404s, fabricates defaults, and writes nothing. */
    @Test
    void repeatedGetsForAnUnknownUserFabricateDefaultsAndPersistNothing() {
        for (int i = 0; i < 2; i++) {
            ResponseEntity<String> response =
                    rest.getForEntity("/api/preferences/unknown-user", String.class);

            assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
            assertThat(response.getBody())
                    .isEqualTo(
                            "{\"userId\":\"unknown-user\",\"theme\":\"light\","
                                    + "\"locale\":\"en-US\",\"emailNotifications\":true}");
        }
        assertThat(rowCount()).isZero();
    }

    /** §3: absent → stored is the only transition, and the first PUT is a first write. */
    @Test
    void putAfterFabricatedGetsBehavesAsAFirstWrite() {
        rest.getForEntity("/api/preferences/u1", String.class);

        ResponseEntity<String> created =
                put("u1", "{\"theme\":\"dark\",\"locale\":\"fr-FR\",\"emailNotifications\":false}");

        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(created.getBody())
                .isEqualTo(
                        "{\"userId\":\"u1\",\"theme\":\"dark\",\"locale\":\"fr-FR\","
                                + "\"emailNotifications\":false}");
        assertThat(rowCount()).isEqualTo(1);

        assertThat(rest.getForEntity("/api/preferences/u1", String.class).getBody())
                .isEqualTo(created.getBody());
    }

    /** §2.2: full replace — an omitted emailNotifications turns the stored true into false. */
    @Test
    void putIsAFullReplaceNotAPatch() {
        put("u1", "{\"theme\":\"dark\",\"locale\":\"fr-FR\",\"emailNotifications\":true}");

        ResponseEntity<String> replaced = put("u1", "{\"theme\":\"light\",\"locale\":\"en-GB\"}");

        assertThat(replaced.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(replaced.getBody())
                .isEqualTo(
                        "{\"userId\":\"u1\",\"theme\":\"light\",\"locale\":\"en-GB\","
                                + "\"emailNotifications\":false}");
        assertThat(rowCount()).isEqualTo(1);
    }

    /** §5: bean-validation failures use the default envelope, which has no message field. */
    @Test
    void validationFailureIs400WithTheDefaultEnvelope() throws Exception {
        ResponseEntity<String> response = put("u1", "{\"theme\":\"  \",\"locale\":\"fr-FR\"}");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertDefaultEnvelope(response.getBody(), 400, "Bad Request", "/api/preferences/u1");
        assertThat(rowCount()).isZero();
    }

    @Test
    void malformedJsonIs400WithTheDefaultEnvelope() throws Exception {
        ResponseEntity<String> response = put("u1", "{\"theme\":");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertDefaultEnvelope(response.getBody(), 400, "Bad Request", "/api/preferences/u1");
    }

    /** §5: the database rejects an over-long key and the monolith's 500 is reproduced. */
    @Test
    void overLongUserIdOnPutIs500WithTheDefaultEnvelope() throws Exception {
        String longId = "x".repeat(150);

        assertThat(rest.getForEntity("/api/preferences/" + longId, String.class).getStatusCode())
                .isEqualTo(HttpStatus.OK);

        ResponseEntity<String> response =
                put(longId, "{\"theme\":\"dark\",\"locale\":\"fr-FR\",\"emailNotifications\":true}");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertDefaultEnvelope(
                response.getBody(), 500, "Internal Server Error", "/api/preferences/" + longId);
        assertThat(rowCount()).isZero();
    }

    @Test
    void exactly100CharacterUserIdIsStored() {
        String id = "x".repeat(100);

        assertThat(
                        put(id, "{\"theme\":\"dark\",\"locale\":\"fr-FR\"}")
                                .getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(rowCount()).isEqualTo(1);
    }

    /** §2.3 / §5: unmapped path and method, both default envelope. */
    @Test
    void unmappedPathAndMethodUseTheDefaultEnvelope() throws Exception {
        ResponseEntity<String> unmapped =
                rest.getForEntity("/api/preferences", String.class);
        assertThat(unmapped.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertDefaultEnvelope(unmapped.getBody(), 404, "Not Found", "/api/preferences");

        ResponseEntity<String> notAllowed =
                rest.exchange(
                        "/api/preferences/u1",
                        HttpMethod.DELETE,
                        HttpEntity.EMPTY,
                        String.class);
        assertThat(notAllowed.getStatusCode()).isEqualTo(HttpStatus.METHOD_NOT_ALLOWED);
        assertDefaultEnvelope(
                notAllowed.getBody(), 405, "Method Not Allowed", "/api/preferences/u1");
    }

    /** §6: health drops the monolith's banner field. */
    @Test
    void healthReportsTheServiceName() {
        ResponseEntity<String> response = rest.getForEntity("/health", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .isEqualTo("{\"status\":\"UP\",\"service\":\"user-preferences-service\"}");
    }

    /** §5: this context never produces the legacy {"error","message"} envelope. */
    private static void assertDefaultEnvelope(String body, int status, String error, String path)
            throws Exception {
        JsonNode json = MAPPER.readTree(body);
        assertThat(json.fieldNames()).toIterable()
                .containsExactlyInAnyOrder("timestamp", "status", "error", "path");
        assertThat(json.get("status").asInt()).isEqualTo(status);
        assertThat(json.get("error").asText()).isEqualTo(error);
        assertThat(json.get("path").asText()).isEqualTo(path);
        assertThat(json.get("timestamp").isTextual()).isTrue();
    }
}

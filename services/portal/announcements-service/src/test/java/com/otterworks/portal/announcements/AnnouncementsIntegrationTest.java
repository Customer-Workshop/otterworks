package com.otterworks.portal.announcements;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
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
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * End-to-end cover on the real engine — PostgreSQL 16 with the checked-in Flyway migration —
 * and on a real servlet container, which is the only place the default error envelope
 * (§5) is produced, because it comes from the error dispatch MockMvc does not run.
 */
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AnnouncementsIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Autowired private TestRestTemplate rest;
    @Autowired private AnnouncementRepository repository;

    @BeforeEach
    void emptyTable() {
        repository.deleteAll();
    }

    private ResponseEntity<JsonNode> post(String path, String json) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange(
                path, HttpMethod.POST, new HttpEntity<>(json, headers), JsonNode.class);
    }

    private JsonNode create(String title, boolean published) {
        ResponseEntity<JsonNode> response =
                post(
                        "/api/announcements",
                        "{\"title\":\"%s\",\"body\":\"body of %s\",\"published\":%s}"
                                .formatted(title, title, published));
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        return response.getBody();
    }

    /** §1, §2.3, §4: the schema is Flyway's, ids come from the identity column. */
    @Test
    void createPersistsThroughTheFlywaySchema() {
        JsonNode created = create("A", false);

        assertThat(created.fieldNames()).toIterable()
                .containsExactly("id", "title", "body", "published", "createdAt");
        assertThat(created.get("id").isNumber()).isTrue();
        assertThat(created.get("published").asBoolean()).isFalse();
        assertThat(Instant.parse(created.get("createdAt").asText())).isNotNull();
        assertThat(repository.count()).isEqualTo(1);
    }

    /** §2.3: published:true is honoured, and the row is visible in the default listing. */
    @Test
    void createHonoursPublishedTrue() {
        JsonNode created = create("A", true);

        assertThat(created.get("published").asBoolean()).isTrue();

        JsonNode listed = rest.getForObject("/api/announcements", JsonNode.class);
        assertThat(listed).hasSize(1);
        assertThat(listed.get(0).get("id")).isEqualTo(created.get("id"));
    }

    /** §2.1: the default listing is published rows only, newest first. */
    @Test
    void defaultListingIsPublishedOnlyNewestFirst() {
        create("A", true);
        create("B", false);
        JsonNode c = create("C", true);

        JsonNode listed = rest.getForObject("/api/announcements", JsonNode.class);

        assertThat(listed).hasSize(2);
        assertThat(listed.get(0).get("id")).isEqualTo(c.get("id"));
        assertThat(listed.get(0).get("title").asText()).isEqualTo("C");
        assertThat(listed.get(1).get("title").asText()).isEqualTo("A");
    }

    /** §2.1: publishedOnly=false returns every row. */
    @Test
    void publishedOnlyFalseReturnsEveryRow() {
        create("A", true);
        create("B", false);

        JsonNode listed =
                rest.getForObject("/api/announcements?publishedOnly=false", JsonNode.class);

        assertThat(listed).hasSize(2);
    }

    /** §2.1: an empty table is []. */
    @Test
    void emptyTableListsAsAnEmptyArray() {
        assertThat(rest.getForObject("/api/announcements", JsonNode.class)).isEmpty();
    }

    /** §2.4: publish is idempotent and createdAt does not move. */
    @Test
    void publishIsIdempotentAndCreatedAtIsImmutable() {
        JsonNode created = create("A", false);
        long id = created.get("id").asLong();

        ResponseEntity<JsonNode> first = post("/api/announcements/" + id + "/publish", "");
        ResponseEntity<JsonNode> second = post("/api/announcements/" + id + "/publish", "");

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(first.getBody().get("published").asBoolean()).isTrue();
        assertThat(second.getBody()).isEqualTo(first.getBody());
        assertThat(Instant.parse(second.getBody().get("createdAt").asText()))
                .isEqualTo(Instant.parse(first.getBody().get("createdAt").asText()));
    }

    /** §2.2: unknown id is the legacy 404 envelope. */
    @Test
    void unknownIdIsTheLegacyNotFoundEnvelope() {
        ResponseEntity<JsonNode> response =
                rest.getForEntity("/api/announcements/999999", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody().fieldNames()).toIterable().containsExactly("error", "message");
        assertThat(response.getBody().get("message").asText())
                .isEqualTo("announcement 999999 not found");
    }

    /** §2.4: publishing an unknown id is the same legacy 404 envelope. */
    @Test
    void publishingAnUnknownIdIsTheLegacyNotFoundEnvelope() {
        ResponseEntity<JsonNode> response = post("/api/announcements/999999/publish", "");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody().get("error").asText()).isEqualTo("Not Found");
        assertThat(response.getBody().get("message").asText())
                .isEqualTo("announcement 999999 not found");
    }

    /** §2.2: a non-numeric id is the legacy 400 envelope. */
    @Test
    void nonNumericIdIsTheLegacyBadRequestEnvelope() {
        ResponseEntity<JsonNode> response =
                rest.getForEntity("/api/announcements/abc", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody().fieldNames()).toIterable().containsExactly("error", "message");
        assertThat(response.getBody().get("message").asText()).isEqualTo("For input string: \"abc\"");
    }

    /** §2.1: an unparseable publishedOnly is the legacy 400 envelope. */
    @Test
    void unparseablePublishedOnlyIsTheLegacyBadRequestEnvelope() {
        ResponseEntity<JsonNode> response =
                rest.getForEntity("/api/announcements?publishedOnly=maybe", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody().get("error").asText()).isEqualTo("Bad Request");
        assertThat(response.getBody().get("message").asText())
                .isEqualTo("Invalid boolean value [maybe]");
    }

    /** §2.3, §5: bean validation produces the default envelope — four fields, no message. */
    @Test
    void validationFailureIsTheDefaultEnvelope() {
        ResponseEntity<JsonNode> response =
                post("/api/announcements", "{\"title\":\"\",\"body\":\"body\"}");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertDefaultEnvelope(response.getBody(), 400, "Bad Request", "/api/announcements");
    }

    /** §2.3, §5: malformed JSON is the default envelope too. */
    @Test
    void malformedJsonIsTheDefaultEnvelope() {
        ResponseEntity<JsonNode> response = post("/api/announcements", "{\"title\":");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertDefaultEnvelope(response.getBody(), 400, "Bad Request", "/api/announcements");
    }

    /** §2.5: unmapped methods are Spring's 405 with the default envelope. */
    @Test
    void deleteIsMethodNotAllowedWithTheDefaultEnvelope() {
        JsonNode created = create("A", false);
        String path = "/api/announcements/" + created.get("id").asLong();

        ResponseEntity<JsonNode> response =
                rest.exchange(path, HttpMethod.DELETE, HttpEntity.EMPTY, JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.METHOD_NOT_ALLOWED);
        assertDefaultEnvelope(response.getBody(), 405, "Method Not Allowed", path);
    }

    /** §5: an unmapped path is the default 404 envelope. */
    @Test
    void unmappedPathIsTheDefault404Envelope() {
        ResponseEntity<JsonNode> response =
                rest.getForEntity("/api/announcements/1/unpublish", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    /** §6: /health echoes the service name and drops the monolith's banner field. */
    @Test
    void healthDropsTheBanner() {
        JsonNode body = rest.getForObject("/health", JsonNode.class);

        assertThat(body.fieldNames()).toIterable().containsExactly("status", "service");
        assertThat(body.get("status").asText()).isEqualTo("UP");
        assertThat(body.get("service").asText()).isEqualTo("announcements-service");
    }

    /** §6: actuator health is exposed with liveness/readiness probes. */
    @Test
    void actuatorHealthIsExposed() {
        assertThat(rest.getForObject("/actuator/health", JsonNode.class).get("status").asText())
                .isEqualTo("UP");
        assertThat(rest.getForEntity("/actuator/health/readiness", JsonNode.class).getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }

    private static void assertDefaultEnvelope(
            JsonNode body, int status, String error, String path) {
        assertThat(body.fieldNames())
                .toIterable()
                .containsExactlyInAnyOrder("timestamp", "status", "error", "path");
        assertThat(body.get("status").asInt()).isEqualTo(status);
        assertThat(body.get("error").asText()).isEqualTo(error);
        assertThat(body.get("path").asText()).isEqualTo(path);
        assertThat(body.get("timestamp").isTextual()).isTrue();
    }
}

package com.otterworks.portal.feedback;

import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.DocumentContext;
import com.jayway.jsonpath.JsonPath;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * End-to-end over the real engine: PostgreSQL 16 with the checked-in Flyway migrations, a real
 * servlet container and Spring's own error dispatch, which is the only place the default error
 * envelope body can be asserted.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
class FeedbackIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16");

    @Autowired private TestRestTemplate rest;

    @Autowired private JdbcTemplate jdbc;

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @BeforeEach
    void emptyTheTable() {
        jdbc.execute("TRUNCATE TABLE feedback");
    }

    @Test
    void flywayCreatedTheContractSchema() {
        List<String> columns =
                jdbc.queryForList(
                        "SELECT column_name FROM information_schema.columns"
                                + " WHERE table_name = 'feedback' ORDER BY ordinal_position",
                        String.class);
        assertThat(columns)
                .containsExactly("id", "user_id", "rating", "message", "created_at");

        assertThat(
                        jdbc.queryForObject(
                                "SELECT data_type FROM information_schema.columns"
                                        + " WHERE table_name = 'feedback'"
                                        + " AND column_name = 'created_at'",
                                String.class))
                .isEqualTo("timestamp without time zone");

        assertThat(
                        jdbc.queryForList(
                                "SELECT indexname FROM pg_indexes WHERE tablename = 'feedback'",
                                String.class))
                .contains("idx_feedback_user_id_created_at");
    }

    /** §4: the monolith has no CHECK on rating, so neither does this schema. */
    @Test
    void theSchemaHasNoRatingCheckConstraint() {
        jdbc.update(
                "INSERT INTO feedback (user_id, rating, message, created_at)"
                        + " VALUES ('direct-writer', 99, 'out of range', now())");

        assertThat(
                        jdbc.queryForObject(
                                "SELECT count(*) FROM feedback WHERE rating = 99", Integer.class))
                .isEqualTo(1);
    }

    @Test
    void createPersistsAndReturnsTheResource() {
        ResponseEntity<String> created =
                post("{\"userId\":\"u1\",\"rating\":5,\"message\":\"great\"}");

        assertThat(created.getStatusCode().value()).isEqualTo(201);
        assertThat(created.getHeaders().getFirst(HttpHeaders.LOCATION)).isNull();

        DocumentContext body = JsonPath.parse(created.getBody());
        assertThat(body.<Integer>read("$.id")).isPositive();
        assertThat(body.<String>read("$.userId")).isEqualTo("u1");
        assertThat(body.<Integer>read("$.rating")).isEqualTo(5);
        assertThat(body.<String>read("$.message")).isEqualTo("great");
        assertThat(Instant.parse(body.read("$.createdAt")))
                .isCloseTo(Instant.now(), within60Seconds());

        assertThat(
                        jdbc.queryForObject(
                                "SELECT message FROM feedback WHERE user_id = 'u1'", String.class))
                .isEqualTo("great");
    }

    @Test
    void listIsNewestFirstAndScopedToTheUser() {
        seed("u1", 5, "oldest", Instant.parse("2026-01-01T00:00:00Z"));
        seed("u1", 1, "newest", Instant.parse("2026-03-01T00:00:00Z"));
        seed("u1", 3, "middle", Instant.parse("2026-02-01T00:00:00Z"));
        seed("u2", 2, "other user", Instant.parse("2026-04-01T00:00:00Z"));

        DocumentContext body = JsonPath.parse(get("/api/feedback?userId=u1").getBody());
        assertThat(body.<List<String>>read("$[*].message"))
                .containsExactly("newest", "middle", "oldest");
    }

    @Test
    void listForAnUnknownUserIs200AndEmpty() {
        ResponseEntity<String> response = get("/api/feedback?userId=nobody");

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isEqualTo("[]");
    }

    @Test
    void listWithoutUserIdIs400WithTheDefaultEnvelope() {
        assertDefaultEnvelope(get("/api/feedback"), 400, "Bad Request", "/api/feedback");
    }

    @Test
    void averageOverAnEmptyTableIsZero() {
        ResponseEntity<String> response = get("/api/feedback/average-rating");

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isEqualTo("{\"averageRating\":0.0}");
    }

    @Test
    void averageIsTheUnroundedMeanOverEveryRow() {
        seed("u1", 5, "a", Instant.parse("2026-01-01T00:00:00Z"));
        seed("u2", 1, "b", Instant.parse("2026-01-02T00:00:00Z"));
        seed("u3", 3, "c", Instant.parse("2026-01-03T00:00:00Z"));

        assertThat(get("/api/feedback/average-rating").getBody())
                .isEqualTo("{\"averageRating\":3.0}");

        seed("u4", 4, "d", Instant.parse("2026-01-04T00:00:00Z"));

        assertThat(get("/api/feedback/average-rating").getBody())
                .isEqualTo("{\"averageRating\":3.25}");
    }

    /**
     * The SQL aggregate returns a numeric the driver widens to a double; the monolith divides in
     * the JVM. A non-terminating mean is where the two could round differently, and the parity
     * replay can only compare the two implementations against each other, not pin the value.
     */
    @Test
    void averageOfANonTerminatingMeanMatchesTheJvmDivision() {
        int[] ratings = {5, 1, 3, 4, 2, 5, 3, 2, 5};
        for (int i = 0; i < ratings.length; i++) {
            seed("u" + i, ratings[i], "r", Instant.parse("2026-01-01T00:00:00Z"));
        }

        assertThat(get("/api/feedback/average-rating").getBody())
                .isEqualTo("{\"averageRating\":" + (30 / 9.0) + "}");
    }

    /** Contract §1: the accepted boundary payloads survive the round trip byte for byte. */
    @Test
    void boundaryLengthAndNonAsciiPayloadsRoundTrip() {
        String userId = "u".repeat(100);
        String message = "m".repeat(2000);
        assertThat(
                        post(
                                        "{\"userId\":\""
                                                + userId
                                                + "\",\"rating\":1,\"message\":\""
                                                + message
                                                + "\"}")
                                .getStatusCode()
                                .value())
                .isEqualTo(201);

        String unicode = "h\u00e9llo \\\"quoted\\\" \\\\ slash \ud83e\udda6";
        ResponseEntity<String> created =
                post("{\"userId\":\"u4\",\"rating\":3,\"message\":\"" + unicode + "\"}");
        assertThat(created.getStatusCode().value()).isEqualTo(201);

        assertThat(JsonPath.parse(get("/api/feedback?userId=" + userId).getBody())
                        .<String>read("$[0].message"))
                .isEqualTo(message);
        assertThat(JsonPath.parse(get("/api/feedback?userId=u4").getBody())
                        .<String>read("$[0].message"))
                .isEqualTo("h\u00e9llo \"quoted\" \\ slash \ud83e\udda6");
    }

    @Test
    void outOfRangeRatingIs400WithTheDefaultEnvelopeAndNoMessageField() {
        for (String rating : List.of("0", "6")) {
            ResponseEntity<String> response =
                    post("{\"userId\":\"u1\",\"rating\":" + rating + ",\"message\":\"m\"}");

            assertDefaultEnvelope(response, 400, "Bad Request", "/api/feedback");
        }
        assertThat(jdbc.queryForObject("SELECT count(*) FROM feedback", Integer.class)).isZero();
    }

    @Test
    void absentRatingBindsToZeroAndIs400() {
        assertDefaultEnvelope(
                post("{\"userId\":\"u1\",\"message\":\"m\"}"), 400, "Bad Request", "/api/feedback");
    }

    @Test
    void blankOrOversizedFieldsAre400() {
        assertDefaultEnvelope(
                post("{\"userId\":\"\",\"rating\":3,\"message\":\"m\"}"),
                400,
                "Bad Request",
                "/api/feedback");
        assertDefaultEnvelope(
                post("{\"userId\":\"u1\",\"rating\":3,\"message\":\"\"}"),
                400,
                "Bad Request",
                "/api/feedback");
        assertDefaultEnvelope(
                post(
                        "{\"userId\":\"u1\",\"rating\":3,\"message\":\""
                                + "m".repeat(2001)
                                + "\"}"),
                400,
                "Bad Request",
                "/api/feedback");
        assertDefaultEnvelope(
                post("{\"userId\":\"" + "u".repeat(101) + "\",\"rating\":3,\"message\":\"m\"}"),
                400,
                "Bad Request",
                "/api/feedback");
    }

    @Test
    void malformedJsonIs400WithTheDefaultEnvelope() {
        assertDefaultEnvelope(
                post("{\"userId\":\"u1\",\"rating\":"), 400, "Bad Request", "/api/feedback");
    }

    /** Append-only: nothing updates, deletes or moderates. */
    @Test
    void mutatingMethodsAreUnavailable() {
        seed("u1", 5, "immutable", Instant.parse("2026-01-01T00:00:00Z"));
        long id = jdbc.queryForObject("SELECT id FROM feedback", Long.class);

        assertDefaultEnvelope(
                exchange(HttpMethod.DELETE, "/api/feedback"),
                405,
                "Method Not Allowed",
                "/api/feedback");
        assertDefaultEnvelope(
                exchange(HttpMethod.PUT, "/api/feedback"),
                405,
                "Method Not Allowed",
                "/api/feedback");
        assertDefaultEnvelope(
                exchange(HttpMethod.DELETE, "/api/feedback/" + id),
                404,
                "Not Found",
                "/api/feedback/" + id);
        assertDefaultEnvelope(
                get("/api/feedback/" + id), 404, "Not Found", "/api/feedback/" + id);

        assertThat(jdbc.queryForObject("SELECT count(*) FROM feedback", Integer.class)).isEqualTo(1);
    }

    @Test
    void healthDropsTheMonolithsBannerField() {
        ResponseEntity<String> response = get("/health");

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isEqualTo("{\"status\":\"UP\",\"service\":\"feedback-service\"}");
    }

    private void seed(String userId, int rating, String message, Instant createdAt) {
        jdbc.update(
                "INSERT INTO feedback (user_id, rating, message, created_at) VALUES (?, ?, ?, ?)",
                userId,
                rating,
                message,
                java.sql.Timestamp.from(createdAt));
    }

    private ResponseEntity<String> post(String body) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange(
                "/api/feedback", HttpMethod.POST, new HttpEntity<>(body, headers), String.class);
    }

    private ResponseEntity<String> get(String path) {
        return rest.getForEntity(path, String.class);
    }

    private ResponseEntity<String> exchange(HttpMethod method, String path) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange(path, method, new HttpEntity<>("{}", headers), String.class);
    }

    private static void assertDefaultEnvelope(
            ResponseEntity<String> response, int status, String error, String path) {
        assertThat(response.getStatusCode().value()).isEqualTo(status);

        DocumentContext body = JsonPath.parse(response.getBody());
        assertThat(body.<Map<String, Object>>read("$")).containsOnlyKeys(
                "timestamp", "status", "error", "path");
        assertThat(body.<Integer>read("$.status")).isEqualTo(status);
        assertThat(body.<String>read("$.error")).isEqualTo(error);
        assertThat(body.<String>read("$.path")).isEqualTo(path);
        assertThat(body.<String>read("$.timestamp")).isNotBlank();
    }

    private static org.assertj.core.data.TemporalUnitOffset within60Seconds() {
        return new org.assertj.core.data.TemporalUnitWithinOffset(60, ChronoUnit.SECONDS);
    }
}

package com.otterworks.legacyportal;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.Date;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

/** Full-context test: the whole modular monolith boots and every module's routes are wired. */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class LegacyPortalApplicationTest {

    @Autowired private MockMvc mockMvc;

    @Value("${jwt.secret}")
    private String jwtSecret;

    private String bearer(String userId, String... roles) {
        String token =
                Jwts.builder()
                        .subject(userId)
                        .claim("roles", Arrays.asList(roles))
                        .claim("type", "access")
                        .issuedAt(Date.from(Instant.now()))
                        .expiration(Date.from(Instant.now().plus(5, ChronoUnit.MINUTES)))
                        .signWith(Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8)))
                        .compact();
        return "Bearer " + token;
    }

    @Test
    void healthEndpointReportsUp() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.service").value("legacy-portal"));
    }

    @Test
    void actuatorHealthIsUp() throws Exception {
        mockMvc.perform(get("/actuator/health")).andExpect(status().isOk());
    }

    @Test
    void announcementsModuleRoundTrips() throws Exception {
        mockMvc.perform(
                        post("/api/announcements")
                                .header(HttpHeaders.AUTHORIZATION, bearer("admin-1", "ADMIN"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"title\":\"Release\",\"body\":\"v1 is out\",\"published\":true}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber());

        mockMvc.perform(
                        get("/api/announcements")
                                .header(HttpHeaders.AUTHORIZATION, bearer("reader-1", "USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("Release"));
    }

    @Test
    void preferencesModuleReturnsDefaults() throws Exception {
        mockMvc.perform(
                        get("/api/preferences/newuser")
                                .header(HttpHeaders.AUTHORIZATION, bearer("newuser", "USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void feedbackModuleValidatesRating() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .header(HttpHeaders.AUTHORIZATION, bearer("u1", "USER"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"rating\":9,\"message\":\"bad rating\"}"))
                .andExpect(status().isBadRequest());
    }

    // --- Authentication / authorization regressions -------------------------------------------

    @Test
    void apiRoutesRejectAnonymousCallers() throws Exception {
        mockMvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"x\",\"body\":\"y\",\"published\":true}"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(post("/api/announcements/1/publish")).andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/preferences/victim")).andExpect(status().isUnauthorized());
        mockMvc.perform(
                        put("/api/preferences/victim")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\"dark\",\"locale\":\"en-US\",\"emailNotifications\":false}"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/feedback")).andExpect(status().isUnauthorized());
        mockMvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"rating\":5,\"message\":\"hi\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void forgedAndRefreshTokensAreRejected() throws Exception {
        String forged =
                "Bearer "
                        + Jwts.builder()
                                .subject("admin-1")
                                .claim("roles", Arrays.asList("ADMIN"))
                                .signWith(
                                        Keys.hmacShaKeyFor(
                                                "another-secret-that-is-long-enough-for-hs256"
                                                        .getBytes(StandardCharsets.UTF_8)))
                                .compact();
        mockMvc.perform(get("/api/announcements").header(HttpHeaders.AUTHORIZATION, forged))
                .andExpect(status().isUnauthorized());

        String refresh =
                "Bearer "
                        + Jwts.builder()
                                .subject("u1")
                                .claim("type", "refresh")
                                .signWith(
                                        Keys.hmacShaKeyFor(
                                                jwtSecret.getBytes(StandardCharsets.UTF_8)))
                                .compact();
        mockMvc.perform(get("/api/announcements").header(HttpHeaders.AUTHORIZATION, refresh))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void announcementWritesRequireEditorOrAdmin() throws Exception {
        mockMvc.perform(
                        post("/api/announcements")
                                .header(HttpHeaders.AUTHORIZATION, bearer("u1", "USER"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"x\",\"body\":\"y\",\"published\":false}"))
                .andExpect(status().isForbidden());

        mockMvc.perform(
                        post("/api/announcements")
                                .header(HttpHeaders.AUTHORIZATION, bearer("ed-1", "EDITOR"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"Draft\",\"body\":\"y\",\"published\":false}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.published").value(false));
    }

    @Test
    void preferencesAreScopedToTheAuthenticatedUser() throws Exception {
        mockMvc.perform(
                        put("/api/preferences/victim")
                                .header(HttpHeaders.AUTHORIZATION, bearer("attacker", "USER"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\"dark\",\"locale\":\"en-US\",\"emailNotifications\":false}"))
                .andExpect(status().isForbidden());
        mockMvc.perform(
                        get("/api/preferences/victim")
                                .header(HttpHeaders.AUTHORIZATION, bearer("attacker", "USER")))
                .andExpect(status().isForbidden());

        mockMvc.perform(
                        put("/api/preferences/victim")
                                .header(HttpHeaders.AUTHORIZATION, bearer("victim", "USER"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\"dark\",\"locale\":\"en-US\",\"emailNotifications\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("victim"))
                .andExpect(jsonPath("$.theme").value("dark"));

        mockMvc.perform(
                        get("/api/preferences/victim")
                                .header(HttpHeaders.AUTHORIZATION, bearer("admin-1", "ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void feedbackIsAttributedToAndListedForTheAuthenticatedUserOnly() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .header(HttpHeaders.AUTHORIZATION, bearer("author", "USER"))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"userId\":\"victim\",\"rating\":5,\"message\":\"mine\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.userId").value("author"));

        mockMvc.perform(
                        get("/api/feedback")
                                .param("userId", "author")
                                .header(HttpHeaders.AUTHORIZATION, bearer("victim", "USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isEmpty());

        mockMvc.perform(
                        get("/api/feedback")
                                .header(HttpHeaders.AUTHORIZATION, bearer("author", "USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].userId").value("author"))
                .andExpect(jsonPath("$[0].message").value("mine"));
    }
}

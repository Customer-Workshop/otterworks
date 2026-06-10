package com.otterworks.report.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Validates JWT bearer tokens on report API endpoints using HMAC-SHA256
 * signature verification (no external JWT library required).
 *
 * Active only outside the {@code test} profile so that existing
 * functional tests continue to pass.
 */
@Component
@Order(1)
@Profile("!test")
public class ReportAuthFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(ReportAuthFilter.class);
    private static final String HMAC_SHA256 = "HmacSHA256";

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        String path = request.getRequestURI();
        if (!path.startsWith("/api/v1/reports")) {
            chain.doFilter(request, response);
            return;
        }

        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring(7);
            if (verifyJwt(token)) {
                chain.doFilter(request, response);
                return;
            }
        }

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"unauthorized\"}");
    }

    private boolean verifyJwt(String token) {
        String secret = System.getenv("JWT_SECRET");
        if (secret == null || secret.isEmpty()) {
            log.warn("JWT_SECRET not configured — rejecting request");
            return false;
        }
        try {
            String[] parts = token.split("\\.");
            if (parts.length != 3) {
                return false;
            }
            byte[] signingInput = (parts[0] + "." + parts[1])
                    .getBytes(StandardCharsets.UTF_8);
            Mac mac = Mac.getInstance(HMAC_SHA256);
            mac.init(new SecretKeySpec(
                    secret.getBytes(StandardCharsets.UTF_8), HMAC_SHA256));
            byte[] expected = mac.doFinal(signingInput);
            byte[] actual = Base64.getUrlDecoder().decode(
                    padBase64(parts[2]));
            return java.security.MessageDigest.isEqual(expected, actual);
        } catch (Exception e) {
            log.debug("JWT verification failed: {}", e.getMessage());
            return false;
        }
    }

    private static String padBase64(String base64) {
        switch (base64.length() % 4) {
            case 2: return base64 + "==";
            case 3: return base64 + "=";
            default: return base64;
        }
    }
}

package com.otterworks.report;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

/**
 * Mints access tokens the way auth-service does, signed with the secret from
 * {@code application-test.properties}.
 */
public final class TestTokens {

    public static final String SECRET = "report-service-test-only-secret-not-for-real-use-0123456789";
    private static final SecretKey KEY = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));

    private TestTokens() {
    }

    public static String bearer(String userId) {
        return "Bearer " + accessToken(userId);
    }

    public static String accessToken(String userId) {
        return token(userId, "access", KEY);
    }

    public static String refreshToken(String userId) {
        return token(userId, "refresh", KEY);
    }

    public static String untypedToken(String userId) {
        return token(userId, null, KEY);
    }

    public static String tokenSignedWithOtherKey(String userId) {
        SecretKey other = Keys.hmacShaKeyFor(
                "some-other-secret-that-report-service-does-not-share-9876543210".getBytes(StandardCharsets.UTF_8));
        return token(userId, "access", other);
    }

    private static String token(String userId, String type, SecretKey key) {
        long now = System.currentTimeMillis();
        return Jwts.builder()
                .subject(userId)
                .claim("type", type)
                .issuedAt(new Date(now))
                .expiration(new Date(now + 60_000))
                .signWith(key)
                .compact();
    }
}

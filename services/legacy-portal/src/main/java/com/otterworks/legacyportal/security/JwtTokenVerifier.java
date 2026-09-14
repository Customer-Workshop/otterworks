package com.otterworks.legacyportal.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;

/**
 * Verifies HS256 access tokens issued by auth-service (same {@code jwt.secret}) and turns them
 * into an {@link Authentication} whose name is the user id and whose authorities are the
 * token's roles prefixed with {@code ROLE_}.
 */
@Component
public class JwtTokenVerifier {

    private static final String ACCESS_TOKEN_TYPE = "access";

    private final SecretKey key;

    public JwtTokenVerifier(@Value("${jwt.secret}") String secret) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    /**
     * @return the authenticated principal, or {@code null} if the token is not a valid access
     *     token
     */
    public Authentication authenticate(String token) {
        Claims claims;
        try {
            claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        } catch (JwtException | IllegalArgumentException e) {
            return null;
        }
        if (!ACCESS_TOKEN_TYPE.equals(claims.get("type", String.class))) {
            return null;
        }
        String userId = claims.getSubject();
        if (userId == null || userId.isEmpty()) {
            return null;
        }
        List<SimpleGrantedAuthority> authorities =
                roles(claims).stream()
                        .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                        .collect(Collectors.toList());
        return new UsernamePasswordAuthenticationToken(userId, null, authorities);
    }

    private static List<String> roles(Claims claims) {
        Object raw = claims.get("roles");
        if (!(raw instanceof List)) {
            return Collections.emptyList();
        }
        return ((List<?>) raw).stream().map(String::valueOf).collect(Collectors.toList());
    }
}

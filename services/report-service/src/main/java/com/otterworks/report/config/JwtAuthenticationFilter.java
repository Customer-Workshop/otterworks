package com.otterworks.report.config;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.JwtParser;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Authenticates requests by verifying the auth-service access token in the
 * {@code Authorization: Bearer} header with the shared {@code JWT_SECRET}. The
 * token subject becomes the principal. Nothing else (in particular no forwarded
 * header) is accepted as identity, so callers that reach the service without
 * going through the gateway still cannot pick their own user id.
 *
 * If no secret is configured every report request is rejected with 401.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(JwtAuthenticationFilter.class);
    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtParser parser;

    public JwtAuthenticationFilter(String secret) {
        if (StringUtils.hasText(secret)) {
            this.parser = Jwts.parser()
                    .verifyWith(Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8)))
                    .build();
        } else {
            this.parser = null;
            log.warn("JWT_SECRET is not set; all report API requests will be rejected");
        }
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String userId = resolveUserId(request.getHeader("Authorization"));
        Authentication existing = SecurityContextHolder.getContext().getAuthentication();
        if (userId != null
                && (existing == null || existing instanceof AnonymousAuthenticationToken)) {
            PreAuthenticatedAuthenticationToken authentication = new PreAuthenticatedAuthenticationToken(
                    userId, "N/A", AuthorityUtils.createAuthorityList("ROLE_USER"));
            authentication.setDetails(request.getRemoteAddr());
            SecurityContextHolder.getContext().setAuthentication(authentication);
        }
        filterChain.doFilter(request, response);
    }

    private String resolveUserId(String authorizationHeader) {
        if (parser == null || authorizationHeader == null
                || !authorizationHeader.regionMatches(true, 0, BEARER_PREFIX, 0, BEARER_PREFIX.length())) {
            return null;
        }
        String token = authorizationHeader.substring(BEARER_PREFIX.length()).trim();
        if (token.isEmpty()) {
            return null;
        }
        try {
            Claims claims = parser.parseSignedClaims(token).getPayload();
            if ("refresh".equals(claims.get("type", String.class))) {
                return null;
            }
            String subject = claims.getSubject();
            if (!StringUtils.hasText(subject)) {
                subject = claims.get("user_id", String.class);
            }
            return StringUtils.hasText(subject) ? subject.trim() : null;
        } catch (JwtException | IllegalArgumentException e) {
            log.debug("Rejected bearer token: {}", e.getMessage());
            return null;
        }
    }
}

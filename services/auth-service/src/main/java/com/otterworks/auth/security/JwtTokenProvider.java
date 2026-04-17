package com.otterworks.auth.security;

import com.otterworks.auth.entity.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.stream.Collectors;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class JwtTokenProvider {

  private final SecretKey key;
  private final long accessTokenExpiry;
  private final long refreshTokenExpiry;

  public JwtTokenProvider(
      @Value("${jwt.secret}") String secret,
      @Value("${jwt.access-token-expiry:3600}") long accessTokenExpiry,
      @Value("${jwt.refresh-token-expiry:604800}") long refreshTokenExpiry) {
    this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    this.accessTokenExpiry = accessTokenExpiry;
    this.refreshTokenExpiry = refreshTokenExpiry;
  }

  public String generateAccessToken(User user) {
    Instant now = Instant.now();
    return Jwts.builder()
        .subject(user.getId().toString())
        .claim("email", user.getEmail())
        .claim("name", user.getDisplayName())
        .claim(
            "roles",
            user.getRoles().stream().map(Enum::name).collect(Collectors.toList()))
        .issuedAt(Date.from(now))
        .expiration(Date.from(now.plus(accessTokenExpiry, ChronoUnit.SECONDS)))
        .signWith(key)
        .compact();
  }

  public String generateRefreshToken(User user) {
    Instant now = Instant.now();
    return Jwts.builder()
        .subject(user.getId().toString())
        .claim("type", "refresh")
        .issuedAt(Date.from(now))
        .expiration(Date.from(now.plus(refreshTokenExpiry, ChronoUnit.SECONDS)))
        .signWith(key)
        .compact();
  }

  public String validateTokenAndGetUserId(String token) {
    Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
    return claims.getSubject();
  }
}

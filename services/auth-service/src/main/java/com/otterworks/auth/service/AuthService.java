package com.otterworks.auth.service;

import com.otterworks.auth.dto.AuthResponse;
import com.otterworks.auth.dto.LoginRequest;
import com.otterworks.auth.dto.RegisterRequest;
import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import com.otterworks.auth.security.JwtTokenProvider;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

  private static final Logger log = LoggerFactory.getLogger(AuthService.class);

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;
  private final JwtTokenProvider jwtTokenProvider;

  public AuthService(
      UserRepository userRepository,
      PasswordEncoder passwordEncoder,
      JwtTokenProvider jwtTokenProvider) {
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
    this.jwtTokenProvider = jwtTokenProvider;
  }

  @Transactional
  public AuthResponse register(RegisterRequest request) {
    if (userRepository.existsByEmail(request.getEmail())) {
      throw new IllegalArgumentException("Email already registered");
    }

    User user = new User();
    user.setEmail(request.getEmail());
    user.setPasswordHash(passwordEncoder.encode(request.getPassword()));
    user.setDisplayName(request.getDisplayName());
    user.setRoles(Set.of(User.Role.USER));
    user = userRepository.save(user);

    log.info("User registered: email={}", user.getEmail());
    return buildAuthResponse(user);
  }

  @Transactional
  public AuthResponse login(LoginRequest request) {
    User user =
        userRepository
            .findByEmail(request.getEmail())
            .orElseThrow(() -> new IllegalArgumentException("Invalid credentials"));

    if (!passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
      throw new IllegalArgumentException("Invalid credentials");
    }

    user.setLastLoginAt(Instant.now());
    userRepository.save(user);

    log.info("User logged in: email={}", user.getEmail());
    return buildAuthResponse(user);
  }

  public AuthResponse refreshToken(String token) {
    String userId = jwtTokenProvider.validateTokenAndGetUserId(token);
    User user =
        userRepository
            .findById(java.util.UUID.fromString(userId))
            .orElseThrow(() -> new IllegalArgumentException("User not found"));
    return buildAuthResponse(user);
  }

  public Map<String, Object> getUserInfo(String token) {
    String userId = jwtTokenProvider.validateTokenAndGetUserId(token);
    User user =
        userRepository
            .findById(java.util.UUID.fromString(userId))
            .orElseThrow(() -> new IllegalArgumentException("User not found"));

    return Map.of(
        "id", user.getId().toString(),
        "email", user.getEmail(),
        "displayName", user.getDisplayName(),
        "roles", user.getRoles(),
        "emailVerified", user.isEmailVerified(),
        "createdAt", user.getCreatedAt().toString());
  }

  public void logout(String token) {
    // In production, add token to a blacklist in Redis
    log.info("User logged out");
  }

  private AuthResponse buildAuthResponse(User user) {
    String accessToken = jwtTokenProvider.generateAccessToken(user);
    String refreshToken = jwtTokenProvider.generateRefreshToken(user);

    return new AuthResponse(
        accessToken,
        refreshToken,
        "Bearer",
        3600,
        new AuthResponse.UserDto(
            user.getId().toString(),
            user.getEmail(),
            user.getDisplayName(),
            user.getAvatarUrl()));
  }
}

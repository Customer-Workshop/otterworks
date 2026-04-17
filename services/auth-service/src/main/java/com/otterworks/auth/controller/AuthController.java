package com.otterworks.auth.controller;

import com.otterworks.auth.dto.AuthResponse;
import com.otterworks.auth.dto.LoginRequest;
import com.otterworks.auth.dto.RegisterRequest;
import com.otterworks.auth.service.AuthService;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

  private final AuthService authService;

  public AuthController(AuthService authService) {
    this.authService = authService;
  }

  @PostMapping("/register")
  public ResponseEntity<AuthResponse> register(@Valid @RequestBody RegisterRequest request) {
    AuthResponse response = authService.register(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  @PostMapping("/login")
  public ResponseEntity<AuthResponse> login(@Valid @RequestBody LoginRequest request) {
    AuthResponse response = authService.login(request);
    return ResponseEntity.ok(response);
  }

  @PostMapping("/refresh")
  public ResponseEntity<AuthResponse> refresh(@RequestHeader("Authorization") String bearerToken) {
    String token = bearerToken.replace("Bearer ", "");
    AuthResponse response = authService.refreshToken(token);
    return ResponseEntity.ok(response);
  }

  @GetMapping("/me")
  public ResponseEntity<Map<String, Object>> me(
      @RequestHeader("Authorization") String bearerToken) {
    String token = bearerToken.replace("Bearer ", "");
    Map<String, Object> userInfo = authService.getUserInfo(token);
    return ResponseEntity.ok(userInfo);
  }

  @PostMapping("/logout")
  public ResponseEntity<Void> logout(@RequestHeader("Authorization") String bearerToken) {
    String token = bearerToken.replace("Bearer ", "");
    authService.logout(token);
    return ResponseEntity.noContent().build();
  }
}

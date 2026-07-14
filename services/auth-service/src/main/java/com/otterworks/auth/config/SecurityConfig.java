package com.otterworks.auth.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.auth.exception.ApiErrorResponse;
import com.otterworks.auth.security.JwtAuthFilter;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

  private final JwtAuthFilter jwtAuthFilter;
  private final ObjectMapper objectMapper;

  public SecurityConfig(JwtAuthFilter jwtAuthFilter, ObjectMapper objectMapper) {
    this.jwtAuthFilter = jwtAuthFilter;
    this.objectMapper = objectMapper;
  }

  @Bean
  public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http.csrf(csrf -> csrf.disable()) // nosemgrep: java.spring.security.audit.spring-csrf-disabled
        .sessionManagement(
            session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers(
                        "/health",
                        "/metrics",
                        "/actuator/health",
                        "/actuator/info",
                        "/actuator/prometheus",
                        "/api/v1/auth/register",
                        "/api/v1/auth/login",
                        "/api/v1/auth/refresh")
                    .permitAll()
                    .requestMatchers("/api/v1/auth/users/lookup", "/api/v1/auth/users/by-id/**")
                    .authenticated()
                    .requestMatchers("/api/v1/auth/users/**")
                    .hasRole("ADMIN")
                    .anyRequest()
                    .authenticated())
        .exceptionHandling(
            exceptions ->
                exceptions
                    .authenticationEntryPoint(
                        (request, response, exception) ->
                            writeError(
                                response, HttpStatus.FORBIDDEN, "FORBIDDEN", "Access denied"))
                    .accessDeniedHandler(
                        (request, response, exception) ->
                            writeError(
                                response, HttpStatus.FORBIDDEN, "FORBIDDEN", "Access denied")))
        .addFilterBefore(jwtAuthFilter, UsernamePasswordAuthenticationFilter.class);
    return http.build();
  }

  @Bean
  public PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
  }

  private void writeError(
      HttpServletResponse response, HttpStatus status, String code, String message)
      throws IOException {
    response.setStatus(status.value());
    response.setContentType("application/json");
    objectMapper.writeValue(
        response.getOutputStream(), ApiErrorResponse.of(code, message, status.value()));
  }
}

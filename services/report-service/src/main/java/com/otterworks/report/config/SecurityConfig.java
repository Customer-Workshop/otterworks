package com.otterworks.report.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.XXssProtectionHeaderWriter;

/**
 * Security configuration.
 *
 * Routes, session policy, CSRF and headers are unchanged from the
 * WebSecurityConfigurerAdapter form this replaced; only the API is new.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http // nosemgrep: java.spring.security.audit.spring-csrf-disabled.spring-csrf-disabled
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health", "/metrics", "/actuator/**").permitAll()
                    .requestMatchers("/swagger-ui/**", "/swagger-resources/**",
                            "/swagger-ui.html", "/v2/api-docs/**", "/v3/api-docs/**").permitAll()
                    .requestMatchers("/api/v1/reports/**").permitAll()  // TODO: Add JWT validation
                    // Spring Security 5 allowed a request that matched no rule; Spring
                    // Security 6 denies it, including the /error dispatch behind a 404
                    // or a 400. permitAll keeps the pre-upgrade outcome per route.
                    .anyRequest().permitAll())
            .headers(headers -> headers
                    .frameOptions(frame -> frame.deny())
                    .contentTypeOptions(Customizer.withDefaults())
                    .xssProtection(xss ->
                            xss.headerValue(XXssProtectionHeaderWriter.HeaderValue.ENABLED_MODE_BLOCK)));

        return http.build();
    }
}

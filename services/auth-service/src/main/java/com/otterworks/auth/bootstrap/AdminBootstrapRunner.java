package com.otterworks.auth.bootstrap;

import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Creates the initial ADMIN account from environment-supplied configuration. Nothing is created
 * when no bootstrap password is configured, and an existing account is never modified.
 */
@Component
public class AdminBootstrapRunner implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(AdminBootstrapRunner.class);
  static final int MIN_PASSWORD_LENGTH = 8;

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;
  private final String email;
  private final String password;
  private final String displayName;

  public AdminBootstrapRunner(
      UserRepository userRepository,
      PasswordEncoder passwordEncoder,
      @Value("${auth.bootstrap-admin.email:}") String email,
      @Value("${auth.bootstrap-admin.password:}") String password,
      @Value("${auth.bootstrap-admin.display-name:Admin User}") String displayName) {
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
    this.email = email == null ? "" : email.trim();
    this.password = password == null ? "" : password;
    this.displayName = displayName;
  }

  @Override
  @Transactional
  public void run(ApplicationArguments args) {
    if (password.isEmpty()) {
      log.info("No bootstrap admin configured (auth.bootstrap-admin.password is unset)");
      return;
    }
    if (email.isEmpty()) {
      throw new IllegalStateException(
          "auth.bootstrap-admin.email must be set when auth.bootstrap-admin.password is set");
    }
    if (password.length() < MIN_PASSWORD_LENGTH) {
      throw new IllegalStateException(
          "auth.bootstrap-admin.password must be at least " + MIN_PASSWORD_LENGTH + " characters");
    }
    if (userRepository.existsByEmail(email)) {
      log.info("Bootstrap admin already exists, leaving it unchanged: email={}", email);
      return;
    }

    User admin = new User();
    admin.setEmail(email);
    admin.setPasswordHash(passwordEncoder.encode(password));
    admin.setDisplayName(displayName);
    admin.setEmailVerified(true);
    admin.setRoles(Set.of(User.Role.ADMIN, User.Role.USER));
    userRepository.save(admin);

    log.info("Bootstrap admin created: email={}", email);
  }
}

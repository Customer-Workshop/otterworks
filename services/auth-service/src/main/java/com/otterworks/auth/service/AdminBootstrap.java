package com.otterworks.auth.service;

import com.otterworks.auth.config.AdminBootstrapConfig;
import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Provisions the bootstrap admin account from configuration instead of a hash committed in a
 * migration. When no password is configured the seeded account stays locked.
 */
@Component
public class AdminBootstrap implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(AdminBootstrap.class);

  private final AdminBootstrapConfig config;
  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;

  public AdminBootstrap(
      AdminBootstrapConfig config, UserRepository userRepository, PasswordEncoder passwordEncoder) {
    this.config = config;
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
  }

  @Override
  @Transactional
  public void run(ApplicationArguments args) {
    String password = config.getPassword();
    if (password == null || password.isBlank()) {
      log.warn(
          "AUTH_BOOTSTRAP_ADMIN_PASSWORD not set; bootstrap admin {} remains locked",
          config.getEmail());
      return;
    }

    User admin =
        userRepository
            .findByEmail(config.getEmail())
            .orElseGet(
                () -> {
                  User u = new User();
                  u.setEmail(config.getEmail());
                  u.setDisplayName(config.getDisplayName());
                  u.setEmailVerified(true);
                  u.setRoles(Set.of(User.Role.ADMIN, User.Role.USER));
                  return u;
                });

    if (admin.getId() != null && passwordEncoder.matches(password, admin.getPasswordHash())) {
      return;
    }

    admin.setPasswordHash(passwordEncoder.encode(password));
    userRepository.save(admin);
    log.info("Bootstrap admin {} provisioned from configuration", config.getEmail());
  }
}

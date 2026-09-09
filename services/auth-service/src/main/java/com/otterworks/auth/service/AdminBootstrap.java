package com.otterworks.auth.service;

import com.otterworks.auth.config.AdminBootstrapConfig;
import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import java.util.HashSet;
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
 * migration. Only a missing account or the locked seed row is touched; an account that already has
 * a real password is never overwritten. When no password is configured the seeded account stays
 * locked.
 */
@Component
public class AdminBootstrap implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(AdminBootstrap.class);

  /** Sentinel written by the migrations; not a valid bcrypt hash so it can never match. */
  static final String LOCKED_PASSWORD_HASH = "!";

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
                  u.setPasswordHash(LOCKED_PASSWORD_HASH);
                  return u;
                });

    if (!LOCKED_PASSWORD_HASH.equals(admin.getPasswordHash())) {
      if (!passwordEncoder.matches(password, admin.getPasswordHash())) {
        log.warn(
            "Bootstrap admin {} already has a password; configured value ignored",
            config.getEmail());
      }
      return;
    }

    Set<User.Role> roles = new HashSet<>(admin.getRoles());
    roles.add(User.Role.ADMIN);
    roles.add(User.Role.USER);
    admin.setRoles(roles);
    admin.setPasswordHash(passwordEncoder.encode(password));
    userRepository.save(admin);
    log.info("Bootstrap admin {} provisioned from configuration", config.getEmail());
  }
}

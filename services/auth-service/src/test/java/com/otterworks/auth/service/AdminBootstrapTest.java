package com.otterworks.auth.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

import com.otterworks.auth.config.AdminBootstrapConfig;
import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

@ExtendWith(MockitoExtension.class)
class AdminBootstrapTest {

  private static final Pattern BCRYPT_HASH = Pattern.compile("\\$2[aby]\\$\\d{2}\\$");

  @Mock private UserRepository userRepository;
  @Mock private PasswordEncoder passwordEncoder;

  private AdminBootstrapConfig config;
  private AdminBootstrap bootstrap;

  @BeforeEach
  void setUp() {
    config = new AdminBootstrapConfig();
    bootstrap = new AdminBootstrap(config, userRepository, passwordEncoder);
  }

  @Test
  void migrations_shouldNotContainBcryptHashes() throws Exception {
    Path migrations = Paths.get("src/main/resources/db/migration");
    try (Stream<Path> files = Files.list(migrations)) {
      for (Path file : files.toList()) {
        String sql = Files.readString(file, StandardCharsets.UTF_8);
        assertThat(BCRYPT_HASH.matcher(sql).find())
            .as("%s must not contain a committed bcrypt hash", file.getFileName())
            .isFalse();
      }
    }
  }

  @Test
  void run_withoutPassword_shouldLeaveSeedAdminLocked() {
    config.setPassword("");

    bootstrap.run(null);

    verify(userRepository, never()).save(any());
    verify(passwordEncoder, never()).encode(anyString());
  }

  @Test
  void run_withPassword_shouldSetHashOnLockedSeedAdmin() {
    config.setPassword("s3cret-from-env");
    User seeded = new User();
    seeded.setId(UUID.randomUUID());
    seeded.setEmail("admin@otterworks.dev");
    seeded.setPasswordHash("!");
    when(userRepository.findByEmail("admin@otterworks.dev")).thenReturn(Optional.of(seeded));
    when(passwordEncoder.encode("s3cret-from-env")).thenReturn("$2a$12$encoded");

    bootstrap.run(null);

    assertThat(seeded.getPasswordHash()).isEqualTo("$2a$12$encoded");
    assertThat(seeded.getRoles()).containsExactlyInAnyOrder(User.Role.ADMIN, User.Role.USER);
    verify(userRepository).save(seeded);
  }

  @Test
  void run_withLockedUserOnlyAccount_shouldAddAdminRole() {
    config.setPassword("s3cret-from-env");
    User seeded = new User();
    seeded.setId(UUID.randomUUID());
    seeded.setEmail("admin@otterworks.dev");
    seeded.setPasswordHash("!");
    seeded.setRoles(Set.of(User.Role.USER));
    when(userRepository.findByEmail("admin@otterworks.dev")).thenReturn(Optional.of(seeded));
    when(passwordEncoder.encode("s3cret-from-env")).thenReturn("$2a$12$encoded");

    bootstrap.run(null);

    assertThat(seeded.getRoles()).containsExactlyInAnyOrder(User.Role.ADMIN, User.Role.USER);
    verify(userRepository).save(seeded);
  }

  @Test
  void run_withExistingUnlockedAccount_shouldNotOverwritePassword() {
    config.setPassword("s3cret-from-env");
    User existing = new User();
    existing.setId(UUID.randomUUID());
    existing.setEmail("admin@otterworks.dev");
    existing.setPasswordHash("$2a$12$someoneelses");
    existing.setRoles(Set.of(User.Role.USER));
    when(userRepository.findByEmail("admin@otterworks.dev")).thenReturn(Optional.of(existing));
    when(passwordEncoder.matches("s3cret-from-env", "$2a$12$someoneelses")).thenReturn(false);

    bootstrap.run(null);

    assertThat(existing.getPasswordHash()).isEqualTo("$2a$12$someoneelses");
    assertThat(existing.getRoles()).containsExactly(User.Role.USER);
    verify(userRepository, never()).save(any());
    verify(passwordEncoder, never()).encode(anyString());
  }

  @Test
  void run_withPassword_shouldCreateAdminWhenMissing() {
    config.setPassword("s3cret-from-env");
    when(userRepository.findByEmail("admin@otterworks.dev")).thenReturn(Optional.empty());
    when(passwordEncoder.encode("s3cret-from-env")).thenReturn("$2a$12$encoded");

    bootstrap.run(null);

    ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
    verify(userRepository).save(captor.capture());
    User created = captor.getValue();
    assertThat(created.getEmail()).isEqualTo("admin@otterworks.dev");
    assertThat(created.getPasswordHash()).isEqualTo("$2a$12$encoded");
    assertThat(created.getRoles()).containsExactlyInAnyOrder(User.Role.ADMIN, User.Role.USER);
  }

  @Test
  void run_withMatchingPassword_shouldNotRehash() {
    config.setPassword("s3cret-from-env");
    User seeded = new User();
    seeded.setId(UUID.randomUUID());
    seeded.setEmail("admin@otterworks.dev");
    seeded.setPasswordHash("$2a$12$existing");
    when(userRepository.findByEmail("admin@otterworks.dev")).thenReturn(Optional.of(seeded));
    when(passwordEncoder.matches("s3cret-from-env", "$2a$12$existing")).thenReturn(true);

    bootstrap.run(null);

    verify(userRepository, never()).save(any());
    verify(passwordEncoder, never()).encode(anyString());
  }
}

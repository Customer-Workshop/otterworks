package com.otterworks.auth.bootstrap;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.security.crypto.password.PasswordEncoder;

@ExtendWith(MockitoExtension.class)
class AdminBootstrapRunnerTest {

  @Mock private UserRepository userRepository;
  @Mock private PasswordEncoder passwordEncoder;

  private AdminBootstrapRunner runner(String email, String password) {
    return new AdminBootstrapRunner(userRepository, passwordEncoder, email, password, "Admin");
  }

  @Test
  void run_shouldNotCreateAnyUserWhenNoPasswordConfigured() {
    runner("admin@otterworks.dev", "").run(new DefaultApplicationArguments());

    verifyNoInteractions(userRepository, passwordEncoder);
  }

  @Test
  void run_shouldCreateAdminWithEncodedPasswordAndAdminRole() {
    when(userRepository.existsByEmail("admin@otterworks.dev")).thenReturn(false);
    when(passwordEncoder.encode("s3cure-bootstrap")).thenReturn("$2a$12$encoded");

    runner("admin@otterworks.dev", "s3cure-bootstrap").run(new DefaultApplicationArguments());

    ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
    verify(userRepository).save(captor.capture());
    User saved = captor.getValue();
    assertThat(saved.getEmail()).isEqualTo("admin@otterworks.dev");
    assertThat(saved.getPasswordHash()).isEqualTo("$2a$12$encoded");
    assertThat(saved.getRoles()).containsExactlyInAnyOrder(User.Role.ADMIN, User.Role.USER);
    assertThat(saved.isEmailVerified()).isTrue();
  }

  @Test
  void run_shouldLeaveExistingAccountUntouched() {
    when(userRepository.existsByEmail("admin@otterworks.dev")).thenReturn(true);

    runner("admin@otterworks.dev", "s3cure-bootstrap").run(new DefaultApplicationArguments());

    verify(userRepository, never()).save(any(User.class));
    verifyNoInteractions(passwordEncoder);
  }

  @Test
  void run_shouldRejectShortPassword() {
    assertThatThrownBy(
            () -> runner("admin@otterworks.dev", "short").run(new DefaultApplicationArguments()))
        .isInstanceOf(IllegalStateException.class);
    verifyNoInteractions(userRepository);
  }

  @Test
  void run_shouldRejectMissingEmail() {
    assertThatThrownBy(() -> runner("", "s3cure-bootstrap").run(new DefaultApplicationArguments()))
        .isInstanceOf(IllegalStateException.class);
    verifyNoInteractions(userRepository);
  }
}

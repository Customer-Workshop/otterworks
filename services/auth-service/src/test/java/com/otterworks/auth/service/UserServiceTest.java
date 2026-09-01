package com.otterworks.auth.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.otterworks.auth.dto.UpdateProfileRequest;
import com.otterworks.auth.dto.UserDTO;
import com.otterworks.auth.entity.User;
import com.otterworks.auth.repository.UserRepository;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

@ExtendWith(MockitoExtension.class)
class UserServiceTest {

  @Mock private UserRepository userRepository;

  @InjectMocks private UserService userService;

  private User testUser;

  @BeforeEach
  void setUp() {
    testUser = new User();
    testUser.setId(UUID.randomUUID());
    testUser.setEmail("test@otterworks.dev");
    testUser.setDisplayName("Test User");
    testUser.setPasswordHash("$2a$12$encodedpassword");
    testUser.setRoles(Set.of(User.Role.USER));
  }

  @Test
  void getProfile_shouldReturnUserDTO() {
    when(userRepository.findById(testUser.getId())).thenReturn(Optional.of(testUser));

    UserDTO dto = userService.getProfile(testUser.getId());

    assertThat(dto.getId()).isEqualTo(testUser.getId().toString());
    assertThat(dto.getEmail()).isEqualTo("test@otterworks.dev");
    assertThat(dto.getDisplayName()).isEqualTo("Test User");
    assertThat(dto.getRoles()).containsExactly("USER");
  }

  @Test
  void getProfile_shouldThrowWhenUserMissing() {
    UUID unknownId = UUID.randomUUID();
    when(userRepository.findById(unknownId)).thenReturn(Optional.empty());

    assertThatThrownBy(() -> userService.getProfile(unknownId))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("User not found");
  }

  @Test
  void updateProfile_shouldUpdateProvidedFields() {
    UpdateProfileRequest request = new UpdateProfileRequest();
    request.setDisplayName("New Name");
    request.setAvatarUrl("https://cdn.otterworks.dev/avatar.png");

    when(userRepository.findById(testUser.getId())).thenReturn(Optional.of(testUser));
    when(userRepository.save(any(User.class))).thenAnswer(inv -> inv.getArgument(0));

    UserDTO dto = userService.updateProfile(testUser.getId(), request);

    assertThat(dto.getDisplayName()).isEqualTo("New Name");
    assertThat(dto.getAvatarUrl()).isEqualTo("https://cdn.otterworks.dev/avatar.png");
    verify(userRepository).save(testUser);
  }

  @Test
  void updateProfile_shouldLeaveOmittedFieldsUnchanged() {
    testUser.setAvatarUrl("https://cdn.otterworks.dev/original.png");
    UpdateProfileRequest request = new UpdateProfileRequest();
    request.setDisplayName("Only Name Changed");

    when(userRepository.findById(testUser.getId())).thenReturn(Optional.of(testUser));
    when(userRepository.save(any(User.class))).thenAnswer(inv -> inv.getArgument(0));

    UserDTO dto = userService.updateProfile(testUser.getId(), request);

    assertThat(dto.getDisplayName()).isEqualTo("Only Name Changed");
    assertThat(dto.getAvatarUrl()).isEqualTo("https://cdn.otterworks.dev/original.png");
  }

  @Test
  void updateProfile_shouldThrowWhenUserMissing() {
    UUID unknownId = UUID.randomUUID();
    when(userRepository.findById(unknownId)).thenReturn(Optional.empty());

    assertThatThrownBy(() -> userService.updateProfile(unknownId, new UpdateProfileRequest()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("User not found");
    verify(userRepository, never()).save(any());
  }

  @Test
  void listUsers_shouldMapEntitiesToDTOs() {
    Page<User> page = new PageImpl<>(List.of(testUser));
    when(userRepository.findAll(any(PageRequest.class))).thenReturn(page);

    Page<UserDTO> result = userService.listUsers(PageRequest.of(0, 20));

    assertThat(result.getTotalElements()).isEqualTo(1);
    assertThat(result.getContent().get(0).getEmail()).isEqualTo("test@otterworks.dev");
  }

  @Test
  void findByEmail_shouldReturnUserDTO() {
    when(userRepository.findByEmail("test@otterworks.dev")).thenReturn(Optional.of(testUser));

    UserDTO dto = userService.findByEmail("test@otterworks.dev");

    assertThat(dto.getId()).isEqualTo(testUser.getId().toString());
  }

  @Test
  void findByEmail_shouldThrowWhenUserMissing() {
    when(userRepository.findByEmail("missing@otterworks.dev")).thenReturn(Optional.empty());

    assertThatThrownBy(() -> userService.findByEmail("missing@otterworks.dev"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("User not found with email: missing@otterworks.dev");
  }
}

package com.otterworks.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ChangePasswordRequest {
  @NotBlank private String currentPassword;

  @NotBlank
  @Size(min = 8, max = 128)
  private String newPassword;
}

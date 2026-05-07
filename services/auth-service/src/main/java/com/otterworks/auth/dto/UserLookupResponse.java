package com.otterworks.auth.dto;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class UserLookupResponse {
  private String id;
  private String email;
  private String displayName;

  public static UserLookupResponse fromUserDTO(UserDTO dto) {
    return new UserLookupResponse(dto.getId(), dto.getEmail(), dto.getDisplayName());
  }
}

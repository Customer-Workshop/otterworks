package com.otterworks.auth.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "auth.bootstrap-admin")
@Getter
@Setter
public class AdminBootstrapConfig {
  private String email = "admin@otterworks.dev";
  private String displayName = "Admin User";
  private String password;
}

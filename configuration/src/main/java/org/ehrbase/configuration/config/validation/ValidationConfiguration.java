package org.ehrbase.configuration.config.validation;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ExternalValidationProperties.class)
public class ValidationConfiguration {
}

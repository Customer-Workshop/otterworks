package com.otterworks.report.lambda;

import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EntityScan(basePackages = "com.otterworks.report.model")
@EnableJpaRepositories(basePackages = "com.otterworks.report.repository")
public class LambdaJpaConfiguration {
}

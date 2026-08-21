package com.otterworks.report.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springdoc.core.models.GroupedOpenApi;

/**
 * OpenAPI 3 configuration using springdoc-openapi.
 *
 * The same controller package is scanned and the same API info is published as before.
 * Swagger UI stays reachable at /swagger-ui.html (springdoc
 * redirects it to /swagger-ui/index.html). The machine-readable document moves from
 * springfox's Swagger 2.0 /v2/api-docs to springdoc's OpenAPI 3 /v3/api-docs: the two
 * are different formats, so the old path is left permitted rather than aliased to a
 * document its callers cannot parse.
 */
@Configuration
public class SwaggerConfig {

    @Bean
    public GroupedOpenApi api() {
        return GroupedOpenApi.builder()
                .group("default")
                .packagesToScan("com.otterworks.report.controller")
                .pathsToMatch("/**")
                .build();
    }

    @Bean
    public OpenAPI apiInfo() {
        return new OpenAPI().info(new Info()
                .title("OtterWorks Report Service API")
                .description("Legacy report generation service for PDF, CSV, and Excel exports")
                .version("0.1.0")
                .contact(new Contact()
                        .name("OtterWorks Engineering")
                        .email("engineering@otterworks.example.com")));
    }
}

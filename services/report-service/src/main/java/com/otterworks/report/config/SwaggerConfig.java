package com.otterworks.report.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * OpenAPI 3 documentation metadata, served by springdoc-openapi.
 *
 * The spec is at /v3/api-docs and the UI at /swagger-ui.html; paths are set in
 * application.properties. Operation-level documentation comes from the
 * io.swagger.v3.oas.annotations on the controller and model classes.
 */
@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI reportServiceOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("OtterWorks Report Service API")
                        .description("Report generation service for PDF, CSV, and Excel exports")
                        .version("0.1.0")
                        .contact(new Contact()
                                .name("OtterWorks Engineering")
                                .email("engineering@otterworks.example.com")));
    }
}

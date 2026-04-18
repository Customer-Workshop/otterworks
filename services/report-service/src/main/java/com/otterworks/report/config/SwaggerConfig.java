package com.otterworks.report.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import springfox.documentation.builders.ApiInfoBuilder;
import springfox.documentation.builders.PathSelectors;
import springfox.documentation.builders.RequestHandlerSelectors;
import springfox.documentation.service.ApiInfo;
import springfox.documentation.service.Contact;
import springfox.documentation.spi.DocumentationType;
import springfox.documentation.spring.web.plugins.Docket;

/**
 * Swagger 2 configuration using SpringFox.
 *
 * LEGACY NOTES:
 * - SpringFox is a dead project (last release: July 2020, version 3.0.0)
 * - Uses Swagger 2 / OpenAPI 2.0 spec
 * - Known to break with Spring Boot 2.6+ (requires patching path-matching)
 * - Requires spring.mvc.pathmatch.matching-strategy=ant-path-matcher workaround
 *
 * UPGRADE TARGET:
 * - Replace with springdoc-openapi 2.x (actively maintained)
 * - Uses OpenAPI 3.0 spec natively
 * - No configuration workarounds needed
 * - Annotations: @Tag, @Operation, @Schema instead of @Api, @ApiOperation, @ApiModel
 */
@Configuration
public class SwaggerConfig {

    @Bean
    public Docket api() {
        return new Docket(DocumentationType.SWAGGER_2)
                .select()
                .apis(RequestHandlerSelectors.basePackage("com.otterworks.report.controller"))
                .paths(PathSelectors.any())
                .build()
                .apiInfo(apiInfo());
    }

    private ApiInfo apiInfo() {
        return new ApiInfoBuilder()
                .title("OtterWorks Report Service API")
                .description("Legacy report generation service for PDF, CSV, and Excel exports")
                .version("0.1.0")
                .contact(new Contact("OtterWorks Engineering", "", "engineering@otterworks.example.com"))
                .build();
    }
}

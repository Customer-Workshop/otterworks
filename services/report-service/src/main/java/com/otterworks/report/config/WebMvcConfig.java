package com.otterworks.report.config;

import com.otterworks.report.security.CallerIdArgumentResolver;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

/**
 * Registers the caller identity argument resolver so controllers can bind the
 * gateway-injected {@code X-User-ID} header.
 */
@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    private final CallerIdArgumentResolver callerIdArgumentResolver;

    public WebMvcConfig(CallerIdArgumentResolver callerIdArgumentResolver) {
        this.callerIdArgumentResolver = callerIdArgumentResolver;
    }

    @Override
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(callerIdArgumentResolver);
    }
}

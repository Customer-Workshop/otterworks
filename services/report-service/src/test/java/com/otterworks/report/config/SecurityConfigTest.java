package com.otterworks.report.config;

import org.junit.jupiter.api.Test;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

public class SecurityConfigTest {

    @Test
    public void securityConfigHasFilterChainBeanMethod() throws NoSuchMethodException {
        Method method = SecurityConfig.class.getDeclaredMethod("filterChain",
                org.springframework.security.config.annotation.web.builders.HttpSecurity.class);
        assertNotNull(method);
        assertEquals(SecurityFilterChain.class, method.getReturnType());
    }

    @Test
    public void securityConfigHasEnableWebSecurityAnnotation() {
        assertNotNull(SecurityConfig.class.getAnnotation(EnableWebSecurity.class));
    }

    @Test
    public void securityConfigIsInstantiable() {
        SecurityConfig config = new SecurityConfig();
        assertNotNull(config);
    }
}

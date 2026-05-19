package com.otterworks.report.config;

import org.junit.Test;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;

import static org.junit.Assert.*;

public class SecurityConfigTest {

    @Test
    public void securityConfigExtendsWebSecurityConfigurerAdapter() {
        assertTrue(WebSecurityConfigurerAdapter.class.isAssignableFrom(SecurityConfig.class));
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

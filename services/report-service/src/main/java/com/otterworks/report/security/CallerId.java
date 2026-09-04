package com.otterworks.report.security;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Binds the authenticated caller id injected by the api-gateway as the
 * {@code X-User-ID} request header to a controller method parameter.
 *
 * A missing or blank header results in a 401 response.
 */
@Documented
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CallerId {
}

package com.otterworks.report.config;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Populates the security context from the identity the API gateway injects after
 * validating the caller's JWT. The gateway overwrites {@code X-User-ID} on every
 * proxied request, so the header is the authoritative caller identity in-service.
 */
public class GatewayIdentityFilter extends OncePerRequestFilter {

    public static final String USER_ID_HEADER = "X-User-ID";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String userId = request.getHeader(USER_ID_HEADER);
        Authentication existing = SecurityContextHolder.getContext().getAuthentication();
        if (StringUtils.hasText(userId)
                && (existing == null || existing instanceof AnonymousAuthenticationToken)) {
            PreAuthenticatedAuthenticationToken authentication = new PreAuthenticatedAuthenticationToken(
                    userId.trim(), "N/A", AuthorityUtils.createAuthorityList("ROLE_USER"));
            authentication.setDetails(request.getRemoteAddr());
            SecurityContextHolder.getContext().setAuthentication(authentication);
        }
        filterChain.doFilter(request, response);
    }
}

package com.otterworks.legacyportal.common;

/**
 * The authenticated caller, forwarded by the API gateway in the {@code X-User-ID} header — the
 * identity convention the rest of the OtterWorks estate already uses (api-gateway sets the header
 * after validating the caller's JWT; file-service, search-service and notification-service read it).
 *
 * <p>{@link CallerIdentityFilter} guarantees the header is present and non-blank on every
 * {@code /api/**} request, so callers of {@link #requireSelf(String, String)} always have a caller
 * id to compare against.
 */
public final class CallerIdentity {

    /** Header name; a compile-time constant so controllers can use it in {@code @RequestHeader}. */
    public static final String HEADER = "X-User-ID";

    private CallerIdentity() {}

    /**
     * Asserts that the caller is acting on its own user-scoped resource.
     *
     * @throws ForbiddenException if the target user id is anyone other than the caller
     */
    public static void requireSelf(String callerId, String targetUserId) {
        if (callerId == null || targetUserId == null || !callerId.trim().equals(targetUserId)) {
            throw new ForbiddenException("caller may only access its own resources");
        }
    }
}

package com.boxoffice.confirmations.domain;

import java.security.SecureRandom;

/** Human-readable references, same alphabet and length as the monolith's {@code com.boxoffice.common.Refs}. */
public final class Refs {

    public static final String ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    private static final char[] CHARS = ALPHABET.toCharArray();
    private static final SecureRandom RANDOM = new SecureRandom();

    private Refs() {
    }

    public static String next(String prefix) {
        StringBuilder sb = new StringBuilder(prefix).append('-');
        for (int i = 0; i < 10; i++) {
            sb.append(CHARS[RANDOM.nextInt(CHARS.length)]);
        }
        return sb.toString();
    }
}

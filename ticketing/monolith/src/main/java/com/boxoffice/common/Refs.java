package com.boxoffice.common;

import java.security.SecureRandom;

/** Human-readable references for holds, orders, tickets and gateway calls. */
public final class Refs {

    private static final char[] ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".toCharArray();
    private static final SecureRandom RANDOM = new SecureRandom();

    private Refs() {
    }

    public static String next(String prefix) {
        StringBuilder sb = new StringBuilder(prefix).append('-');
        for (int i = 0; i < 10; i++) {
            sb.append(ALPHABET[RANDOM.nextInt(ALPHABET.length)]);
        }
        return sb.toString();
    }
}

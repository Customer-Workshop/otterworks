package com.boxoffice.payments.gateway;

import java.security.SecureRandom;

/** Human-readable references, same alphabet and shape as the monolith (PAY-XXXXXXXXXX, GW-XXXXXXXXXX). */
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

package com.otterworks.ticketing.seats.config;

import java.security.SecureRandom;

/** Same reference alphabet and length as the monolith's com.boxoffice.common.Refs. */
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

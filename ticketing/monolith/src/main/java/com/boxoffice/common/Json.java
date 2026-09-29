package com.boxoffice.common;

import java.util.Collection;
import java.util.Map;

/** Minimal JSON writer for the kiosk API (the app predates a JSON-B dependency). */
public final class Json {

    private Json() {
    }

    public static String write(Object o) {
        StringBuilder sb = new StringBuilder();
        append(sb, o);
        return sb.toString();
    }

    private static void append(StringBuilder sb, Object o) {
        if (o == null) {
            sb.append("null");
        } else if (o instanceof Number || o instanceof Boolean) {
            sb.append(o);
        } else if (o instanceof Map<?, ?> m) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if (!first) {
                    sb.append(',');
                }
                first = false;
                str(sb, String.valueOf(e.getKey()));
                sb.append(':');
                append(sb, e.getValue());
            }
            sb.append('}');
        } else if (o instanceof Collection<?> c) {
            sb.append('[');
            boolean first = true;
            for (Object x : c) {
                if (!first) {
                    sb.append(',');
                }
                first = false;
                append(sb, x);
            }
            sb.append(']');
        } else {
            str(sb, String.valueOf(o));
        }
    }

    private static void str(StringBuilder sb, String s) {
        sb.append('"');
        for (char ch : s.toCharArray()) {
            switch (ch) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        sb.append(String.format("\\u%04x", (int) ch));
                    } else {
                        sb.append(ch);
                    }
                }
            }
        }
        sb.append('"');
    }
}

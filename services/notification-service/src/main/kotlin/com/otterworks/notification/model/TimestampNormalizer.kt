package com.otterworks.notification.model

import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Normalizes timestamps to RFC 3339 strings. Legacy events emitted by older
 * service versions carry Unix epoch numbers (seconds or milliseconds) in the
 * timestamp field; these are converted to ISO-8601 strings.
 */
object TimestampNormalizer {
    private const val EPOCH_MILLIS_THRESHOLD = 100_000_000_000L

    fun normalize(value: String): String {
        val epoch = value.toLongOrNull() ?: return value
        val instant = if (epoch >= EPOCH_MILLIS_THRESHOLD) {
            Instant.ofEpochMilli(epoch)
        } else {
            Instant.ofEpochSecond(epoch)
        }
        return DateTimeFormatter.ISO_INSTANT.format(instant)
    }
}

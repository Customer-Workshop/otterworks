using System.Globalization;

namespace OtterWorks.ReportService.Utilities;

public static class ReportDateUtils
{
    private static readonly string[] IsoFormats =
    [
        "yyyy-MM-dd'T'HH:mm:ss'Z'",
        "yyyy-MM-ddTHH:mm:ssZ",
        "yyyy-MM-ddTHH:mm:sszzz",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd",
    ];

    public static string? ToIsoString(DateTime? date)
    {
        if (date == null)
        {
            return null;
        }

        return date.Value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
    }

    public static string ToDisplayString(DateTime? date)
    {
        if (date == null)
        {
            return "N/A";
        }

        return date.Value.ToUniversalTime().ToString("MMM dd, yyyy HH:mm", CultureInfo.InvariantCulture);
    }

    public static string ToFileNameString(DateTime? date)
    {
        var d = date ?? DateTime.UtcNow;
        return d.ToUniversalTime().ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture);
    }

    public static DateTime ParseIsoDate(string dateString)
    {
        if (string.IsNullOrWhiteSpace(dateString))
        {
            throw new ArgumentException("Date string cannot be null or empty", nameof(dateString));
        }

        if (DateTime.TryParseExact(
            dateString,
            IsoFormats,
            CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
            out var result))
        {
            return result;
        }

        throw new ArgumentException($"Cannot parse date: {dateString}", nameof(dateString));
    }

    public static DateTime StartOfToday()
    {
        return DateTime.UtcNow.Date;
    }

    public static DateTime StartOfMonth()
    {
        var now = DateTime.UtcNow;
        return new DateTime(now.Year, now.Month, 1, 0, 0, 0, DateTimeKind.Utc);
    }

    public static DateTime DaysAgo(int days)
    {
        return DateTime.UtcNow.AddDays(-days);
    }

    public static bool IsWithinRange(DateTime date, DateTime start, DateTime end)
    {
        return date >= start && date <= end;
    }

    public static string HumanReadableDuration(DateTime start, DateTime end)
    {
        var diff = end - start;
        long totalSeconds = (long)diff.TotalSeconds;
        long minutes = totalSeconds / 60;
        long hours = minutes / 60;

        if (hours > 0)
        {
            return $"{hours}h {minutes % 60}m";
        }

        if (minutes > 0)
        {
            return $"{minutes}m {totalSeconds % 60}s";
        }

        return $"{totalSeconds}s";
    }
}

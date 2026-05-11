using System.Globalization;

namespace OtterWorks.ReportService.Util;

public static class ReportDateUtils
{
    public static string ToIsoString(DateTime? date)
    {
        if (date == null) return string.Empty;
        return date.Value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
    }

    public static string ToDisplayString(DateTime? date)
    {
        if (date == null) return "N/A";
        return date.Value.ToUniversalTime().ToString("MMM dd, yyyy HH:mm", CultureInfo.InvariantCulture);
    }

    public static string ToFileNameString(DateTime date)
    {
        return date.ToUniversalTime().ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture);
    }

    public static DateTime DaysAgo(int days)
    {
        return DateTime.UtcNow.AddDays(-days);
    }

    public static string HumanReadableDuration(DateTime start, DateTime end)
    {
        var diff = end - start;
        if (diff.TotalHours >= 1)
        {
            return $"{(int)diff.TotalHours}h {diff.Minutes}m";
        }
        if (diff.TotalMinutes >= 1)
        {
            return $"{(int)diff.TotalMinutes}m {diff.Seconds}s";
        }
        return $"{(int)diff.TotalSeconds}s";
    }

    public static string FormatColumnName(string columnName)
    {
        if (string.IsNullOrWhiteSpace(columnName)) return string.Empty;
        var replaced = columnName.Replace("_", " ");
        return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(replaced);
    }

    public static string BuildFileName(string reportName, string extension)
    {
        var safeName = System.Text.RegularExpressions.Regex.Replace(reportName, "[^a-zA-Z0-9]", "_").ToLowerInvariant();
        return $"{safeName}_{ToFileNameString(DateTime.UtcNow)}.{extension}";
    }
}

using System.Globalization;
using System.Text;
using CsvHelper;
using CsvHelper.Configuration;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Utilities;

namespace OtterWorks.ReportService.Services;

public class CsvReportGenerator : ICsvReportGenerator
{
    private readonly ILogger<CsvReportGenerator> _logger;

    public CsvReportGenerator(ILogger<CsvReportGenerator> logger)
    {
        _logger = logger;
    }

    public string GenerateCsv(Report report, List<Dictionary<string, object>> data, string outputDir)
    {
        string fileName = BuildFileName(report, "csv");
        string filePath = Path.Combine(outputDir, fileName);
        Directory.CreateDirectory(outputDir);

        using var writer = new StreamWriter(filePath, false, Encoding.UTF8);
        using var csv = new CsvWriter(writer, new CsvConfiguration(CultureInfo.InvariantCulture));

        if (data.Count > 0)
        {
            var columns = data[0].Keys.ToList();

            writer.WriteLine($"# OtterWorks Report: {report.ReportName}");
            writer.WriteLine($"# Generated: {ReportDateUtils.ToDisplayString(DateTime.UtcNow)}");
            writer.WriteLine($"# Period: {ReportDateUtils.ToDisplayString(report.DateFrom)} to {ReportDateUtils.ToDisplayString(report.DateTo)}");
            writer.WriteLine($"# Rows: {data.Count}");
            writer.WriteLine();

            foreach (string col in columns)
            {
                csv.WriteField(col);
            }

            csv.NextRecord();

            foreach (var row in data)
            {
                foreach (string col in columns)
                {
                    string value = row.TryGetValue(col, out var val) && val != null
                        ? Convert.ToString(val, CultureInfo.InvariantCulture) ?? string.Empty
                        : string.Empty;
                    csv.WriteField(value);
                }

                csv.NextRecord();
            }
        }

        _logger.LogInformation("Generated CSV report: {FilePath} ({Size} bytes)", filePath, new FileInfo(filePath).Length);
        return filePath;
    }

    private static string BuildFileName(Report report, string extension)
    {
        string safeName = System.Text.RegularExpressions.Regex.Replace(report.ReportName, "[^a-zA-Z0-9]", "_").ToLowerInvariant();
        return $"{safeName}_{ReportDateUtils.ToFileNameString(DateTime.UtcNow)}.{extension}";
    }
}

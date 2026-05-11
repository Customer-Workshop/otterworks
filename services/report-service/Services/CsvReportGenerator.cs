using System.Globalization;
using System.Text;
using CsvHelper;
using CsvHelper.Configuration;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Util;

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
        var fileName = ReportDateUtils.BuildFileName(report.ReportName, "csv");
        var outputPath = Path.Combine(outputDir, fileName);
        Directory.CreateDirectory(outputDir);

        using var writer = new StreamWriter(outputPath, false, Encoding.UTF8);
        using var csv = new CsvWriter(writer, new CsvConfiguration(CultureInfo.InvariantCulture));

        if (data.Count > 0)
        {
            var columns = data[0].Keys.ToList();

            writer.WriteLine($"# OtterWorks Report: {report.ReportName}");
            writer.WriteLine($"# Generated: {ReportDateUtils.ToDisplayString(DateTime.UtcNow)}");
            writer.WriteLine($"# Period: {ReportDateUtils.ToDisplayString(report.DateFrom)} to {ReportDateUtils.ToDisplayString(report.DateTo)}");
            writer.WriteLine($"# Rows: {data.Count}");
            writer.WriteLine();

            foreach (var col in columns)
            {
                csv.WriteField(col);
            }
            csv.NextRecord();

            foreach (var row in data)
            {
                foreach (var col in columns)
                {
                    var value = row.TryGetValue(col, out var v) ? v?.ToString() ?? "" : "";
                    csv.WriteField(value);
                }
                csv.NextRecord();
            }
        }

        writer.Flush();
        var fileInfo = new FileInfo(outputPath);
        _logger.LogInformation("Generated CSV report: {Path} ({Bytes} bytes)", outputPath, fileInfo.Length);
        return outputPath;
    }
}

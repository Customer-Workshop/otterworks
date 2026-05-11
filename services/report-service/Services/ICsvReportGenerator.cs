using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Services;

public interface ICsvReportGenerator
{
    string GenerateCsv(Report report, List<Dictionary<string, object>> data, string outputDir);
}

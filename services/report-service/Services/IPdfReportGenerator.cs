using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Services;

public interface IPdfReportGenerator
{
    string GeneratePdf(Report report, List<Dictionary<string, object>> data, string outputDir);
}

using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Services;

public interface IExcelReportGenerator
{
    string GenerateExcel(Report report, List<Dictionary<string, object>> data, string outputDir);
}

namespace OtterWorks.ReportService.Services;

public interface IReportGenerationWorker
{
    void EnqueueReport(long reportId);
}

using System.Text.Json;
using System.Threading.Channels;
using Microsoft.Extensions.Options;
using OtterWorks.ReportService.Configuration;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Utilities;

namespace OtterWorks.ReportService.Services;

public class ReportGenerationWorker : BackgroundService
{
    private readonly Channel<long> _channel;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<ReportGenerationWorker> _logger;
    private readonly ReportSettings _settings;

    public ReportGenerationWorker(
        Channel<long> channel,
        IServiceScopeFactory scopeFactory,
        ILogger<ReportGenerationWorker> logger,
        IOptions<ReportSettings> settings)
    {
        _channel = channel;
        _scopeFactory = scopeFactory;
        _logger = logger;
        _settings = settings.Value;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await foreach (long reportId in _channel.Reader.ReadAllAsync(stoppingToken))
        {
            try
            {
                await ProcessReportAsync(reportId);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unhandled error processing report {ReportId}", reportId);
            }
        }
    }

    public async Task ProcessReportAsync(long reportId)
    {
        using var scope = _scopeFactory.CreateScope();
        var repository = scope.ServiceProvider.GetRequiredService<IReportRepository>();
        var dataFetcher = scope.ServiceProvider.GetRequiredService<IReportDataFetcher>();
        var pdfGenerator = scope.ServiceProvider.GetRequiredService<IPdfReportGenerator>();
        var csvGenerator = scope.ServiceProvider.GetRequiredService<ICsvReportGenerator>();
        var excelGenerator = scope.ServiceProvider.GetRequiredService<IExcelReportGenerator>();

        var report = await repository.GetByIdAsync(reportId);
        if (report == null)
        {
            _logger.LogError("Report not found for generation: {ReportId}", reportId);
            return;
        }

        report.Status = ReportStatus.GENERATING;
        await repository.UpdateAsync(report);

        try
        {
            Dictionary<string, string>? parameters = null;
            if (report.Parameters != null)
            {
                parameters = JsonSerializer.Deserialize<Dictionary<string, string>>(report.Parameters);
            }

            var data = await FetchDataForCategoryAsync(dataFetcher, report.Category, report.DateFrom ?? DateTime.UtcNow.AddDays(-30), report.DateTo ?? DateTime.UtcNow, parameters);

            if (data.Count > _settings.MaxRows)
            {
                data = data.Take(_settings.MaxRows).ToList();
                _logger.LogWarning("Report {ReportId} truncated to {MaxRows} rows", reportId, _settings.MaxRows);
            }

            string filePath = GenerateFile(report, data, pdfGenerator, csvGenerator, excelGenerator);

            var fileInfo = new FileInfo(filePath);
            report.Status = ReportStatus.COMPLETED;
            report.CompletedAt = DateTime.UtcNow;
            report.FilePath = filePath;
            report.FileSizeBytes = fileInfo.Length;
            report.RowCount = data.Count;
            await repository.UpdateAsync(report);

            string duration = ReportDateUtils.HumanReadableDuration(report.CreatedAt, report.CompletedAt.Value);
            _logger.LogInformation(
                "Report {ReportId} completed: {RowCount} rows, {FileSize} bytes, took {Duration}",
                reportId,
                data.Count,
                fileInfo.Length,
                duration);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Report generation failed for {ReportId}: {Message}", reportId, ex.Message);
            report.Status = ReportStatus.FAILED;
            report.CompletedAt = DateTime.UtcNow;
            report.ErrorMessage = ex.Message;
            await repository.UpdateAsync(report);
        }
    }

    private static async Task<List<Dictionary<string, object>>> FetchDataForCategoryAsync(
        IReportDataFetcher dataFetcher,
        ReportCategory category,
        DateTime dateFrom,
        DateTime dateTo,
        Dictionary<string, string>? parameters)
    {
        return category switch
        {
            ReportCategory.USAGE_ANALYTICS or ReportCategory.COLLABORATION_METRICS or ReportCategory.SYSTEM_HEALTH =>
                await dataFetcher.FetchAnalyticsDataAsync(dateFrom, dateTo, parameters),
            ReportCategory.AUDIT_LOG or ReportCategory.COMPLIANCE =>
                await dataFetcher.FetchAuditDataAsync(dateFrom, dateTo, parameters),
            ReportCategory.USER_ACTIVITY or ReportCategory.STORAGE_SUMMARY =>
                await dataFetcher.FetchUserActivityDataAsync(dateFrom, dateTo, parameters),
            _ => throw new ArgumentException($"Unsupported category: {category}"),
        };
    }

    private string GenerateFile(
        Report report,
        List<Dictionary<string, object>> data,
        IPdfReportGenerator pdfGenerator,
        ICsvReportGenerator csvGenerator,
        IExcelReportGenerator excelGenerator)
    {
        string outputDir = _settings.OutputDir;
        return report.ReportType switch
        {
            Models.ReportType.PDF => pdfGenerator.GeneratePdf(report, data, outputDir),
            Models.ReportType.CSV => csvGenerator.GenerateCsv(report, data, outputDir),
            Models.ReportType.EXCEL => excelGenerator.GenerateExcel(report, data, outputDir),
            _ => throw new ArgumentException($"Unsupported report type: {report.ReportType}"),
        };
    }
}

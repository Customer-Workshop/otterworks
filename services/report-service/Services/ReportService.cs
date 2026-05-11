using System.Text.Json;
using System.Threading.Channels;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Utilities;

namespace OtterWorks.ReportService.Services;

public class ReportService : IReportService
{
    private readonly IReportRepository _repository;
    private readonly Channel<long> _generationChannel;
    private readonly ILogger<ReportService> _logger;

    public ReportService(
        IReportRepository repository,
        Channel<long> generationChannel,
        ILogger<ReportService> logger)
    {
        _repository = repository;
        _generationChannel = generationChannel;
        _logger = logger;
    }

    public async Task<Report> CreateReportAsync(ReportRequest request)
    {
        var report = new Report
        {
            ReportName = request.ReportName!,
            Category = request.Category!.Value,
            ReportType = request.ReportType!.Value,
            RequestedBy = request.RequestedBy!,
            Status = ReportStatus.PENDING,
            CreatedAt = DateTime.UtcNow,
            DateFrom = request.DateFrom ?? ReportDateUtils.DaysAgo(30),
            DateTo = request.DateTo ?? DateTime.UtcNow,
        };

        if (request.Parameters != null)
        {
            report.Parameters = JsonSerializer.Serialize(request.Parameters);
        }

        var saved = await _repository.AddAsync(report);
        _logger.LogInformation(
            "Created report request: id={Id}, name={Name}, type={Type}",
            saved.Id,
            saved.ReportName,
            saved.ReportType);

        await _generationChannel.Writer.WriteAsync(saved.Id);

        return saved;
    }

    public async Task<Report?> GetReportAsync(long id)
    {
        return await _repository.GetByIdAsync(id);
    }

    public async Task<List<Report>> GetReportsByUserAsync(string userId)
    {
        return await _repository.GetByUserAsync(userId);
    }

    public async Task<List<Report>> GetReportsByStatusAsync(ReportStatus status)
    {
        return await _repository.GetByStatusAsync(status);
    }

    public async Task<bool> DeleteReportAsync(long id)
    {
        var report = await _repository.GetByIdAsync(id);
        if (report == null)
        {
            return false;
        }

        string? filePath = report.FilePath;

        bool deleted = await _repository.DeleteAsync(id);
        if (!deleted)
        {
            return false;
        }

        _logger.LogInformation("Deleted report: {Id}", id);

        if (filePath != null && File.Exists(filePath))
        {
            try
            {
                File.Delete(filePath);
            }
            catch (IOException ex)
            {
                _logger.LogWarning(ex, "Failed to delete report file: {FilePath}", filePath);
            }
        }

        return true;
    }
}

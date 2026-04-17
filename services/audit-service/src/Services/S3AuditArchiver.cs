using Microsoft.Extensions.Options;
using OtterWorks.AuditService.Config;

namespace OtterWorks.AuditService.Services;

public class S3AuditArchiver : IAuditArchiver
{
    private readonly AwsSettings _settings;
    private readonly ILogger<S3AuditArchiver> _logger;

    public S3AuditArchiver(IOptions<AwsSettings> settings, ILogger<S3AuditArchiver> logger)
    {
        _settings = settings.Value;
        _logger = logger;
    }

    public Task<string> ExportToS3Async(DateTime startDate, DateTime endDate, string? userId)
    {
        // TODO: Query audit events, serialize to JSON/CSV, upload to S3
        _logger.LogInformation("Exporting audit events to S3: {StartDate} - {EndDate}, userId={UserId}", startDate, endDate, userId);
        var key = $"audit-exports/{startDate:yyyy-MM-dd}_{endDate:yyyy-MM-dd}_{Guid.NewGuid():N}.json";
        return Task.FromResult($"s3://{_settings.S3ArchiveBucket}/{key}");
    }
}

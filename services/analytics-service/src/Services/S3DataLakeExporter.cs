using System.Text;
using System.Text.Json;
using Amazon.S3;
using Amazon.S3.Model;
using Microsoft.Extensions.Options;
using OtterWorks.AnalyticsService.Config;

namespace OtterWorks.AnalyticsService.Services;

public class S3DataLakeExporter : IDataLakeExporter
{
    private readonly IAmazonS3 _s3Client;
    private readonly AwsSettings _awsSettings;
    private readonly IMetricsRepository _repository;
    private readonly ILogger<S3DataLakeExporter> _logger;

    public S3DataLakeExporter(
        IAmazonS3 s3Client,
        IOptions<AwsSettings> awsSettings,
        IMetricsRepository repository,
        ILogger<S3DataLakeExporter> logger)
    {
        _s3Client = s3Client;
        _awsSettings = awsSettings.Value;
        _repository = repository;
        _logger = logger;
    }

    public async Task ExportAsync(string period)
    {
        try
        {
            var data = await _repository.GetExportDataAsync(period);
            if (data.Count == 0)
            {
                _logger.LogInformation("No data to export for period={Period}", period);
                return;
            }

            var json = JsonSerializer.Serialize(data);
            var key = $"analytics/export/{DateTime.UtcNow:yyyy/MM/dd}/{DateTime.UtcNow:HHmmss}_{period}.json";

            using var stream = new MemoryStream(Encoding.UTF8.GetBytes(json));
            var request = new PutObjectRequest
            {
                BucketName = _awsSettings.DataLakeBucket,
                Key = key,
                InputStream = stream,
                ContentType = "application/json",
            };

            await _s3Client.PutObjectAsync(request);
            _logger.LogInformation("Exported {Count} records to S3: {Key}", data.Count, key);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to export data to S3 for period={Period}", period);
        }
    }
}

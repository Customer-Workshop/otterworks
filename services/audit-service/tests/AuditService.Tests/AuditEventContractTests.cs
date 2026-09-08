using System.Text.Json;
using Amazon.S3;
using Amazon.S3.Model;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.AuditService.Config;
using OtterWorks.AuditService.Models;
using OtterWorks.AuditService.Services;

namespace AuditService.Tests;

/// <summary>
/// Verifies that every JSON shape audit-service publishes (REST responses and S3 export/archive
/// documents) conforms to shared/events/schemas/audit-events.json#/definitions/AuditEvent.
/// </summary>
public class AuditEventContractTests
{
    // ASP.NET Core minimal APIs serialize responses with JsonSerializerDefaults.Web.
    private static readonly JsonSerializerOptions ResponseJson = new(JsonSerializerDefaults.Web);

    private readonly JsonElement _schema = JsonSchemaAssert.LoadDefinition("audit-events.json", "AuditEvent");

    private readonly Mock<IAuditRepository> _repository = new();
    private readonly Mock<IAmazonS3> _s3 = new();
    private readonly IOptions<AwsSettings> _options = Options.Create(new AwsSettings
    {
        Region = "us-east-1",
        DynamoDbTable = "test-table",
        S3ArchiveBucket = "test-bucket",
        ArchiveAfterDays = 90,
    });

    private static readonly List<AuditEvent> SampleEvents = new()
    {
        new()
        {
            Id = Guid.NewGuid().ToString(),
            UserId = "user-1",
            Action = "share",
            ResourceType = "file",
            ResourceId = "file-1",
            Details = new Dictionary<string, string> { ["sharedWithUserId"] = "user-2" },
            IpAddress = "10.0.0.1",
            UserAgent = "curl/8.0",
            Timestamp = DateTime.UtcNow,
        },
        new()
        {
            Id = Guid.NewGuid().ToString(),
            UserId = "system",
            Action = "unknown",
            ResourceType = "unknown",
            ResourceId = string.Empty,
            Timestamp = DateTime.UtcNow.AddDays(-1),
        },
    };

    [Fact]
    public async Task RecordEventAsync_ResponseConformsToAuditEventContract()
    {
        _repository.Setup(r => r.SaveEventAsync(It.IsAny<AuditEvent>())).Returns(Task.CompletedTask);
        var service = new OtterWorks.AuditService.Services.AuditService(
            _repository.Object,
            Mock.Of<IAuditArchiver>(),
            _options,
            Mock.Of<ILogger<OtterWorks.AuditService.Services.AuditService>>());

        var response = await service.RecordEventAsync(new AuditEventRequest
        {
            UserId = "user-123",
            Action = "create",
            ResourceType = "document",
            ResourceId = "doc-456",
            Details = new Dictionary<string, string> { ["source"] = "contract-test" },
        });

        var payload = JsonSerializer.SerializeToElement(response, ResponseJson);

        JsonSchemaAssert.ConformsTo(_schema, payload);
    }

    [Fact]
    public async Task ExportAsync_JsonDocumentConformsToAuditEventContract()
    {
        var from = DateTime.UtcNow.AddDays(-7);
        var to = DateTime.UtcNow;
        _repository.Setup(r => r.GetEventsByDateRangeAsync(from, to)).ReturnsAsync(SampleEvents);
        var archiver = new S3AuditArchiver(_s3.Object, _repository.Object, _options, Mock.Of<ILogger<S3AuditArchiver>>());

        var body = await CaptureUploadedBodyAsync(() => archiver.ExportAsync(from, to, "json"));

        using var doc = JsonDocument.Parse(body);
        Assert.Equal(JsonValueKind.Array, doc.RootElement.ValueKind);
        Assert.Equal(SampleEvents.Count, doc.RootElement.GetArrayLength());
        foreach (var element in doc.RootElement.EnumerateArray())
        {
            JsonSchemaAssert.ConformsTo(_schema, element);
        }
    }

    [Fact]
    public async Task ArchiveOldEventsAsync_JsonDocumentConformsToAuditEventContract()
    {
        var olderThan = DateTime.UtcNow.AddDays(-90);
        _repository.Setup(r => r.GetEventsByDateRangeAsync(DateTime.MinValue, olderThan)).ReturnsAsync(SampleEvents);
        _repository.Setup(r => r.DeleteEventsAsync(It.IsAny<IEnumerable<string>>())).ReturnsAsync(SampleEvents.Count);
        var archiver = new S3AuditArchiver(_s3.Object, _repository.Object, _options, Mock.Of<ILogger<S3AuditArchiver>>());

        var body = await CaptureUploadedBodyAsync(() => archiver.ArchiveOldEventsAsync(olderThan));

        using var doc = JsonDocument.Parse(body);
        foreach (var element in doc.RootElement.EnumerateArray())
        {
            JsonSchemaAssert.ConformsTo(_schema, element);
        }
    }

    [Fact]
    public void ExportAndResponseSerializersAgreeOnFieldNames()
    {
        var entity = SampleEvents[0];

        var exported = JsonSerializer.SerializeToElement(entity, S3AuditArchiver.ExportJsonOptions);
        var responded = JsonSerializer.SerializeToElement(AuditEventResponse.FromEntity(entity), ResponseJson);

        Assert.Equal(
            responded.EnumerateObject().Select(p => p.Name).OrderBy(n => n),
            exported.EnumerateObject().Select(p => p.Name).OrderBy(n => n));
    }

    [Fact]
    public void PascalCaseSerializationIsRejectedByContract()
    {
        var legacy = JsonSerializer.SerializeToElement(SampleEvents[0], new JsonSerializerOptions { WriteIndented = true });

        var violations = JsonSchemaAssert.Validate(_schema, legacy, "$");

        Assert.Contains(violations, v => v.Contains("missing required property 'userId'"));
        Assert.Contains(violations, v => v.Contains("'UserId' is not declared"));
    }

    private async Task<string> CaptureUploadedBodyAsync(Func<Task> action)
    {
        string? body = null;
        _s3.Setup(s => s.PutObjectAsync(It.IsAny<PutObjectRequest>(), default))
            .Callback<PutObjectRequest, CancellationToken>((req, _) => body = req.ContentBody)
            .ReturnsAsync(new PutObjectResponse());

        await action();

        Assert.NotNull(body);
        return body!;
    }
}

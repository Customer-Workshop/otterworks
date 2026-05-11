using FluentAssertions;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.Unit;

public class SqsConsumerNormalizationTests
{
    [Fact]
    public void NormalizeEvent_DocumentCreated_MapsToIndexDocument()
    {
        var body = new Dictionary<string, object?>
        {
            ["event_type"] = "document_created",
            ["payload"] = new Dictionary<string, object?>
            {
                ["id"] = "doc-1",
                ["title"] = "Test",
            },
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("index_document");
    }

    [Fact]
    public void NormalizeEvent_FileDeleted_MapsToDelete()
    {
        var body = new Dictionary<string, object?>
        {
            ["event_type"] = "file_deleted",
            ["payload"] = new Dictionary<string, object?> { ["id"] = "file-1", ["type"] = "file" },
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("delete");
    }

    [Fact]
    public void NormalizeEvent_CamelCaseFileUploaded_MapsToIndexFile()
    {
        var body = new Dictionary<string, object?>
        {
            ["eventType"] = "file_uploaded",
            ["fileId"] = "file-2",
            ["name"] = "report.pdf",
            ["mimeType"] = "application/pdf",
            ["ownerId"] = "user-1",
            ["folderId"] = "folder-1",
            ["sizeBytes"] = 1024,
            ["timestamp"] = "2024-01-01T00:00:00Z",
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("index_file");
        normalized.Should().ContainKey("data");
    }

    [Fact]
    public void NormalizeEvent_CamelCaseFileDeleted_MapsToDelete()
    {
        var body = new Dictionary<string, object?>
        {
            ["eventType"] = "file_deleted",
            ["fileId"] = "file-3",
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("delete");
    }

    [Fact]
    public void NormalizeEvent_NoEventType_ReturnsOriginal()
    {
        var body = new Dictionary<string, object?>
        {
            ["action"] = "index_document",
            ["data"] = new Dictionary<string, object?> { ["id"] = "doc-1", ["title"] = "Test" },
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("index_document");
    }

    [Fact]
    public void NormalizeEvent_DocumentUpdated_MapsToIndexDocument()
    {
        var body = new Dictionary<string, object?>
        {
            ["event_type"] = "document_updated",
            ["payload"] = new Dictionary<string, object?> { ["id"] = "doc-1", ["title"] = "Updated" },
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("index_document");
    }

    [Fact]
    public void NormalizeEvent_FileRestored_MapsToIndexFile()
    {
        var body = new Dictionary<string, object?>
        {
            ["event_type"] = "file_restored",
            ["payload"] = new Dictionary<string, object?> { ["id"] = "file-1", ["name"] = "restored.pdf" },
        };

        var normalized = SqsConsumerService.NormalizeEvent(body);
        normalized["action"]!.ToString().Should().Be("index_file");
    }
}

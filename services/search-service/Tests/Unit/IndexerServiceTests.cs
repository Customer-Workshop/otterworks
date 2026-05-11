using FluentAssertions;
using Moq;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.Unit;

public class IndexerServiceTests
{
    private readonly Mock<IMeiliSearchService> _mockSearch = new();
    private readonly Mock<IHttpClientFactory> _mockHttpFactory = new();
    private readonly IndexerService _service;

    public IndexerServiceTests()
    {
        _service = new IndexerService(_mockSearch.Object, _mockHttpFactory.Object);
    }

    [Fact]
    public void IndexDocument_ValidPayload_IndexesAndReturnsStatus()
    {
        var payload = new Dictionary<string, object?>
        {
            ["id"] = "doc-1",
            ["title"] = "My Doc",
            ["content"] = "body text",
            ["owner_id"] = "user-1",
            ["tags"] = new List<string> { "work" },
        };

        var result = _service.IndexDocument(payload);
        result["status"].Should().Be("indexed");
        result["id"].Should().Be("doc-1");
        result["type"].Should().Be("document");
        _mockSearch.Verify(s => s.IndexDocument(It.IsAny<Dictionary<string, object?>>()), Times.Once);
    }

    [Fact]
    public void IndexDocument_MissingId_ThrowsArgumentException()
    {
        var payload = new Dictionary<string, object?> { ["title"] = "No ID" };
        Action act = () => _service.IndexDocument(payload);
        act.Should().Throw<ArgumentException>().WithMessage("*id*");
    }

    [Fact]
    public void IndexDocument_MissingTitle_ThrowsArgumentException()
    {
        var payload = new Dictionary<string, object?> { ["id"] = "doc-1" };
        Action act = () => _service.IndexDocument(payload);
        act.Should().Throw<ArgumentException>().WithMessage("*title*");
    }

    [Fact]
    public void IndexFile_ValidPayload_IndexesAndReturnsStatus()
    {
        var payload = new Dictionary<string, object?>
        {
            ["id"] = "file-1",
            ["name"] = "report.pdf",
            ["mime_type"] = "application/pdf",
            ["owner_id"] = "user-1",
        };

        var result = _service.IndexFile(payload);
        result["status"].Should().Be("indexed");
        result["id"].Should().Be("file-1");
        result["type"].Should().Be("file");
    }

    [Fact]
    public void IndexFile_MissingId_ThrowsArgumentException()
    {
        var payload = new Dictionary<string, object?> { ["name"] = "No ID" };
        Action act = () => _service.IndexFile(payload);
        act.Should().Throw<ArgumentException>().WithMessage("*id*");
    }

    [Fact]
    public void IndexFile_MissingName_ThrowsArgumentException()
    {
        var payload = new Dictionary<string, object?> { ["id"] = "file-1" };
        Action act = () => _service.IndexFile(payload);
        act.Should().Throw<ArgumentException>().WithMessage("*name*");
    }

    [Fact]
    public void Remove_ValidDocument_CallsDeleteAndReturnsStatus()
    {
        _mockSearch.Setup(s => s.DeleteDocument("document", "doc-1")).Returns(true);
        var result = _service.Remove("document", "doc-1");
        result["status"]!.ToString().Should().Be("deleted");
    }

    [Fact]
    public void Remove_NotFoundDocument_ReturnsNotFoundStatus()
    {
        _mockSearch.Setup(s => s.DeleteDocument("document", "doc-missing")).Returns(false);
        var result = _service.Remove("document", "doc-missing");
        result["status"]!.ToString().Should().Be("not_found");
    }

    [Fact]
    public void Remove_InvalidType_ThrowsArgumentException()
    {
        Action act = () => _service.Remove("invalid", "doc-1");
        act.Should().Throw<ArgumentException>().WithMessage("*Invalid type*");
    }

    [Fact]
    public void ProcessEvent_IndexDocument_ProcessesCorrectly()
    {
        var eventData = new Dictionary<string, object?>
        {
            ["action"] = "index_document",
            ["data"] = new Dictionary<string, object?>
            {
                ["id"] = "doc-2",
                ["title"] = "Event Doc",
            },
        };

        var result = _service.ProcessEvent(eventData);
        result.Should().NotBeNull();
        _mockSearch.Verify(s => s.IndexDocument(It.IsAny<Dictionary<string, object?>>()), Times.Once);
    }

    [Fact]
    public void ProcessEvent_Delete_ProcessesCorrectly()
    {
        _mockSearch.Setup(s => s.DeleteDocument("document", "doc-3")).Returns(true);
        var eventData = new Dictionary<string, object?>
        {
            ["action"] = "delete",
            ["data"] = new Dictionary<string, object?>
            {
                ["type"] = "document",
                ["id"] = "doc-3",
            },
        };

        var result = _service.ProcessEvent(eventData);
        result.Should().NotBeNull();
    }

    [Fact]
    public void ProcessEvent_UnknownAction_ReturnsNull()
    {
        var eventData = new Dictionary<string, object?>
        {
            ["action"] = "unknown_action",
            ["data"] = new Dictionary<string, object?>(),
        };

        var result = _service.ProcessEvent(eventData);
        result.Should().BeNull();
    }
}

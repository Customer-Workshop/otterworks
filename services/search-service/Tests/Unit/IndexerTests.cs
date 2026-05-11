using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;

namespace SearchService.Tests.Unit;

public class IndexerTests
{
    private readonly Mock<IMeilisearchService> _mockSearch;
    private readonly Mock<IHttpClientFactory> _mockHttpFactory;
    private readonly Indexer _indexer;

    public IndexerTests()
    {
        _mockSearch = new Mock<IMeilisearchService>();
        _mockHttpFactory = new Mock<IHttpClientFactory>();
        _indexer = new Indexer(
            _mockSearch.Object,
            _mockHttpFactory.Object,
            Mock.Of<ILogger<Indexer>>());

        _mockSearch.Setup(x => x.IndexDocumentAsync(It.IsAny<Dictionary<string, object?>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);
        _mockSearch.Setup(x => x.IndexFileAsync(It.IsAny<Dictionary<string, object?>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);
        _mockSearch.Setup(x => x.DeleteDocumentAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);
    }

    [Fact]
    public async Task IndexDocument_Success()
    {
        var result = await _indexer.IndexDocumentAsync(new IndexDocumentRequest
        {
            Id = "doc-1",
            Title = "Test Doc",
            Content = "Hello world",
            OwnerId = "user-1",
        });

        Assert.Equal("indexed", result.Status);
        Assert.Equal("document", result.Type);
    }

    [Fact]
    public async Task IndexDocument_MissingId_Throws()
    {
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            _indexer.IndexDocumentAsync(new IndexDocumentRequest { Title = "No ID" }));
        Assert.Contains("id", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task IndexDocument_MissingTitle_Throws()
    {
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            _indexer.IndexDocumentAsync(new IndexDocumentRequest { Id = "doc-1" }));
        Assert.Contains("title", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task IndexFile_Success()
    {
        var result = await _indexer.IndexFileAsync(new IndexFileRequest
        {
            Id = "file-1",
            Name = "report.pdf",
            MimeType = "application/pdf",
            OwnerId = "user-1",
        });

        Assert.Equal("indexed", result.Status);
        Assert.Equal("file", result.Type);
    }

    [Fact]
    public async Task IndexFile_MissingId_Throws()
    {
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            _indexer.IndexFileAsync(new IndexFileRequest { Name = "report.pdf" }));
        Assert.Contains("id", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task IndexFile_MissingName_Throws()
    {
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            _indexer.IndexFileAsync(new IndexFileRequest { Id = "file-1" }));
        Assert.Contains("name", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Remove_Document_ReturnsDeleted()
    {
        var result = await _indexer.RemoveAsync("document", "doc-1");
        Assert.Equal("deleted", result.Status);
        Assert.Equal("document", result.Type);
    }

    [Fact]
    public async Task Remove_InvalidType_Throws()
    {
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            _indexer.RemoveAsync("invalid", "id-1"));
        Assert.Contains("Invalid type", ex.Message);
    }

    [Fact]
    public async Task ProcessEvent_IndexDocument()
    {
        var result = await _indexer.ProcessEventAsync(new Dictionary<string, object?>
        {
            ["action"] = "index_document",
            ["data"] = System.Text.Json.JsonSerializer.Deserialize<object>(
                System.Text.Json.JsonSerializer.Serialize(new { id = "doc-1", title = "Test" })),
        });

        Assert.NotNull(result);
        Assert.Equal("indexed", result!.Status);
    }

    [Fact]
    public async Task ProcessEvent_IndexFile()
    {
        var result = await _indexer.ProcessEventAsync(new Dictionary<string, object?>
        {
            ["action"] = "index_file",
            ["data"] = System.Text.Json.JsonSerializer.Deserialize<object>(
                System.Text.Json.JsonSerializer.Serialize(new { id = "file-1", name = "test.pdf" })),
        });

        Assert.NotNull(result);
        Assert.Equal("indexed", result!.Status);
    }

    [Fact]
    public async Task ProcessEvent_Delete()
    {
        var result = await _indexer.ProcessEventAsync(new Dictionary<string, object?>
        {
            ["action"] = "delete",
            ["data"] = System.Text.Json.JsonSerializer.Deserialize<object>(
                System.Text.Json.JsonSerializer.Serialize(new { id = "doc-1", type = "document" })),
        });

        Assert.NotNull(result);
        Assert.Equal("deleted", result!.Status);
    }

    [Fact]
    public async Task ProcessEvent_UnknownAction_ReturnsNull()
    {
        var result = await _indexer.ProcessEventAsync(new Dictionary<string, object?>
        {
            ["action"] = "unknown",
            ["data"] = new Dictionary<string, object?>(),
        });

        Assert.Null(result);
    }
}

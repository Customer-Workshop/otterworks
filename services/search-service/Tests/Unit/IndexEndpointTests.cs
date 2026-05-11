using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Moq;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;

namespace SearchService.Tests.Unit;

public class IndexEndpointTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly TestWebApplicationFactory _factory;

    public IndexEndpointTests(TestWebApplicationFactory factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task IndexDocument_Success_Returns201()
    {
        _factory.MockIndexer.Setup(x => x.IndexDocumentAsync(It.IsAny<IndexDocumentRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new IndexResult { Status = "indexed", Id = "doc-123", Type = "document" });

        var body = JsonSerializer.Serialize(new
        {
            id = "doc-123",
            title = "My Document",
            content = "Document body text",
            owner_id = "user-1",
            tags = new[] { "work" },
        });

        var response = await _client.PostAsync("/api/v1/search/index/document",
            new StringContent(body, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("indexed", json.GetProperty("status").GetString());
        Assert.Equal("doc-123", json.GetProperty("id").GetString());
        Assert.Equal("document", json.GetProperty("type").GetString());
    }

    [Fact]
    public async Task IndexDocument_MissingBody_Returns400()
    {
        var response = await _client.PostAsync("/api/v1/search/index/document",
            new StringContent(string.Empty, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task IndexDocument_MissingId_Returns400()
    {
        _factory.MockIndexer.Setup(x => x.IndexDocumentAsync(It.IsAny<IndexDocumentRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ArgumentException("Document 'id' is required"));

        var body = JsonSerializer.Serialize(new { title = "No ID Doc" });
        var response = await _client.PostAsync("/api/v1/search/index/document",
            new StringContent(body, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task IndexDocument_MissingTitle_Returns400()
    {
        _factory.MockIndexer.Setup(x => x.IndexDocumentAsync(It.IsAny<IndexDocumentRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ArgumentException("Document 'title' is required"));

        var body = JsonSerializer.Serialize(new { id = "doc-no-title" });
        var response = await _client.PostAsync("/api/v1/search/index/document",
            new StringContent(body, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task IndexFile_Success_Returns201()
    {
        _factory.MockIndexer.Setup(x => x.IndexFileAsync(It.IsAny<IndexFileRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new IndexResult { Status = "indexed", Id = "file-123", Type = "file" });

        var body = JsonSerializer.Serialize(new
        {
            id = "file-123",
            name = "report.pdf",
            mime_type = "application/pdf",
            owner_id = "user-1",
            folder_id = "folder-1",
            tags = new[] { "report" },
            size = 1024,
        });

        var response = await _client.PostAsync("/api/v1/search/index/file",
            new StringContent(body, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("indexed", json.GetProperty("status").GetString());
        Assert.Equal("file-123", json.GetProperty("id").GetString());
        Assert.Equal("file", json.GetProperty("type").GetString());
    }

    [Fact]
    public async Task IndexFile_MissingName_Returns400()
    {
        _factory.MockIndexer.Setup(x => x.IndexFileAsync(It.IsAny<IndexFileRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ArgumentException("File 'name' is required"));

        var body = JsonSerializer.Serialize(new { id = "file-no-name" });
        var response = await _client.PostAsync("/api/v1/search/index/file",
            new StringContent(body, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task DeleteDocument_Returns200()
    {
        _factory.MockIndexer.Setup(x => x.RemoveAsync("document", "doc-123", It.IsAny<CancellationToken>()))
            .ReturnsAsync(new IndexResult { Status = "deleted", Id = "doc-123", Type = "document" });

        var response = await _client.DeleteAsync("/api/v1/search/index/document/doc-123");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("deleted", json.GetProperty("status").GetString());
    }

    [Fact]
    public async Task DeleteInvalidType_Returns400()
    {
        _factory.MockIndexer.Setup(x => x.RemoveAsync("invalid", "doc-123", It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ArgumentException("Invalid type 'invalid'. Must be 'document' or 'file'."));

        var response = await _client.DeleteAsync("/api/v1/search/index/invalid/doc-123");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Reindex_Returns200()
    {
        _factory.MockIndexer.Setup(x => x.ReindexAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ReindexResult
            {
                Status = "reindexed",
                Indices = ["documents", "files"],
                IndexedCounts = new Dictionary<string, int> { ["documents"] = 0, ["files"] = 0 },
            });

        var response = await _client.PostAsync("/api/v1/search/reindex", null);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("reindexed", json.GetProperty("status").GetString());
    }
}

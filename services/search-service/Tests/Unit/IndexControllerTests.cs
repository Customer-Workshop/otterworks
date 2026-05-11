using System.Text;
using FluentAssertions;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Moq;
using OtterWorks.SearchService.Controllers;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.Unit;

public class IndexControllerTests
{
    private readonly Mock<IIndexerService> _mockIndexer = new();
    private readonly IndexController _controller;

    public IndexControllerTests()
    {
        _controller = new IndexController(_mockIndexer.Object);
    }

    private void SetRequestBody(string json)
    {
        var context = new DefaultHttpContext();
        context.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        context.Request.ContentType = "application/json";
        _controller.ControllerContext = new ControllerContext { HttpContext = context };
    }

    private void SetEmptyRequestBody()
    {
        var context = new DefaultHttpContext();
        context.Request.Body = new MemoryStream(Array.Empty<byte>());
        _controller.ControllerContext = new ControllerContext { HttpContext = context };
    }

    [Fact]
    public void IndexDocument_Success_Returns201()
    {
        SetRequestBody("{\"id\":\"doc-123\",\"title\":\"My Document\",\"content\":\"body\",\"owner_id\":\"user-1\",\"tags\":[\"work\"]}");
        _mockIndexer.Setup(i => i.IndexDocument(It.IsAny<Dictionary<string, object?>>()))
            .Returns(new Dictionary<string, string> { ["status"] = "indexed", ["id"] = "doc-123", ["type"] = "document" });

        var result = _controller.IndexDocument() as ObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(201);
    }

    [Fact]
    public void IndexDocument_EmptyBody_Returns400()
    {
        SetEmptyRequestBody();
        var result = _controller.IndexDocument() as BadRequestObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void IndexDocument_MissingId_Returns400()
    {
        SetRequestBody("{\"title\":\"No ID Doc\"}");
        _mockIndexer.Setup(i => i.IndexDocument(It.IsAny<Dictionary<string, object?>>()))
            .Throws(new ArgumentException("Document 'id' is required"));

        var result = _controller.IndexDocument() as BadRequestObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void IndexDocument_MissingTitle_Returns400()
    {
        SetRequestBody("{\"id\":\"doc-no-title\"}");
        _mockIndexer.Setup(i => i.IndexDocument(It.IsAny<Dictionary<string, object?>>()))
            .Throws(new ArgumentException("Document 'title' is required"));

        var result = _controller.IndexDocument() as BadRequestObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void IndexFile_Success_Returns201()
    {
        SetRequestBody("{\"id\":\"file-123\",\"name\":\"report.pdf\",\"mime_type\":\"application/pdf\",\"owner_id\":\"user-1\"}");
        _mockIndexer.Setup(i => i.IndexFile(It.IsAny<Dictionary<string, object?>>()))
            .Returns(new Dictionary<string, string> { ["status"] = "indexed", ["id"] = "file-123", ["type"] = "file" });

        var result = _controller.IndexFile() as ObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(201);
    }

    [Fact]
    public void IndexFile_MissingName_Returns400()
    {
        SetRequestBody("{\"id\":\"file-no-name\"}");
        _mockIndexer.Setup(i => i.IndexFile(It.IsAny<Dictionary<string, object?>>()))
            .Throws(new ArgumentException("File 'name' is required"));

        var result = _controller.IndexFile() as BadRequestObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void DeleteFromIndex_DocumentFound_Returns200()
    {
        _controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        _mockIndexer.Setup(i => i.Remove("document", "doc-123"))
            .Returns(new Dictionary<string, object?> { ["status"] = "deleted", ["id"] = "doc-123", ["type"] = "document" });

        var result = _controller.RemoveFromIndex("document", "doc-123") as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void DeleteFromIndex_InvalidType_Returns400()
    {
        _controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        _mockIndexer.Setup(i => i.Remove("invalid", "doc-123"))
            .Throws(new ArgumentException("Invalid type 'invalid'. Must be 'document' or 'file'."));

        var result = _controller.RemoveFromIndex("invalid", "doc-123") as BadRequestObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void Reindex_Success_Returns200()
    {
        _controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        _mockIndexer.Setup(i => i.Reindex())
            .Returns(new Dictionary<string, object?> { ["status"] = "reindexed" });

        var result = _controller.ReindexAll() as OkObjectResult;
        result.Should().NotBeNull();
    }
}

using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.DocumentService.Data;
using OtterWorks.DocumentService.DTOs;
using OtterWorks.DocumentService.Services;

namespace DocumentService.Tests.Unit;

public class DocumentServiceTests : IDisposable
{
    private readonly DocumentDbContext _db;
    private readonly OtterWorks.DocumentService.Services.DocumentService _service;
    private readonly Guid _ownerId = Guid.NewGuid();
    private readonly Guid _folderId = Guid.NewGuid();

    public DocumentServiceTests()
    {
        var options = new DbContextOptionsBuilder<DocumentDbContext>()
            .UseInMemoryDatabase("TestDb_" + Guid.NewGuid().ToString())
            .Options;
        _db = new DocumentDbContext(options);
        var mockPublisher = new Mock<IEventPublisher>();
        mockPublisher.Setup(p => p.PublishAsync(It.IsAny<string>(), It.IsAny<Dictionary<string, object>>()))
            .Returns(Task.CompletedTask);
        var mockLogger = new Mock<ILogger<OtterWorks.DocumentService.Services.DocumentService>>();
        _service = new OtterWorks.DocumentService.Services.DocumentService(_db, mockPublisher.Object, mockLogger.Object);
    }

    public void Dispose()
    {
        _db.Dispose();
    }

    [Fact]
    public async Task CreateAndGet_ReturnsDocument()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "Service Test",
            Content = "Body text",
            OwnerId = _ownerId,
        });

        Assert.Equal("Service Test", doc.Title);
        Assert.Equal(2, doc.WordCount);
        Assert.Equal(1, doc.Version);

        var fetched = await _service.GetAsync(doc.Id);
        Assert.NotNull(fetched);
        Assert.Equal(doc.Id, fetched!.Id);
    }

    [Fact]
    public async Task ListDocuments_WithFilters()
    {
        var otherOwner = Guid.NewGuid();
        await _service.CreateAsync(new DocumentCreateRequest { Title = "A", Content = "", OwnerId = _ownerId, FolderId = _folderId });
        await _service.CreateAsync(new DocumentCreateRequest { Title = "B", Content = "", OwnerId = _ownerId });
        await _service.CreateAsync(new DocumentCreateRequest { Title = "C", Content = "", OwnerId = otherOwner });

        var (items1, total1) = await _service.ListAsync(_ownerId, null, 1, 20);
        Assert.Equal(2, total1);

        var (items2, total2) = await _service.ListAsync(null, _folderId, 1, 20);
        Assert.Equal(1, total2);
    }

    [Fact]
    public async Task Update_CreatesVersion()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "V1",
            Content = "First",
            OwnerId = _ownerId,
        });

        var updated = await _service.UpdateAsync(doc.Id, new DocumentUpdateRequest
        {
            Title = "V2",
            Content = "Second",
        });

        Assert.NotNull(updated);
        Assert.Equal(2, updated!.Version);
        Assert.Equal("V2", updated.Title);

        var versions = await _service.ListVersionsAsync(doc.Id);
        Assert.Equal(2, versions.Count);
    }

    [Fact]
    public async Task Patch_PartialUpdate()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "Original",
            Content = "Body",
            ContentType = "text/plain",
            OwnerId = _ownerId,
        });

        var patched = await _service.PatchAsync(doc.Id, new DocumentPatchRequest
        {
            Title = "New Title",
            ProvidedFields = new HashSet<string> { "title" },
        });

        Assert.NotNull(patched);
        Assert.Equal("New Title", patched!.Title);
        Assert.Equal("Body", patched.Content);
        Assert.Equal(2, patched.Version);
    }

    [Fact]
    public async Task SoftDelete_HidesDocument()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "Delete Me",
            Content = "",
            OwnerId = _ownerId,
        });

        Assert.True(await _service.DeleteAsync(doc.Id));
        Assert.Null(await _service.GetAsync(doc.Id));
    }

    [Fact]
    public async Task Delete_Nonexistent_ReturnsFalse()
    {
        Assert.False(await _service.DeleteAsync(Guid.NewGuid()));
    }

    [Fact]
    public async Task RestoreVersion_RestoresContent()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "Orig Title",
            Content = "Orig Content",
            OwnerId = _ownerId,
        });

        var versions = await _service.ListVersionsAsync(doc.Id);
        var v1Id = versions[0].Id;

        await _service.UpdateAsync(doc.Id, new DocumentUpdateRequest { Title = "Changed", Content = "New" });

        var restored = await _service.RestoreVersionAsync(doc.Id, v1Id);
        Assert.NotNull(restored);
        Assert.Equal("Orig Title", restored!.Title);
        Assert.Equal("Orig Content", restored.Content);
        Assert.Equal(3, restored.Version);
    }

    [Fact]
    public async Task ExportFormats()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "Export Test",
            Content = "Some text",
            OwnerId = _ownerId,
        });

        var (htmlBody, htmlCt) = _service.ExportDocument(doc, "html");
        Assert.Contains("<h1>Export Test</h1>", htmlBody);
        Assert.Equal("text/html", htmlCt);

        var (mdBody, mdCt) = _service.ExportDocument(doc, "markdown");
        Assert.Contains("# Export Test", mdBody);
        Assert.Equal("text/markdown", mdCt);

        var (pdfBody, pdfCt) = _service.ExportDocument(doc, "pdf");
        Assert.Contains("TITLE: Export Test", pdfBody);
        Assert.Equal("application/pdf", pdfCt);
    }

    [Fact]
    public async Task Comments_CRUD()
    {
        var doc = await _service.CreateAsync(new DocumentCreateRequest
        {
            Title = "Commented",
            Content = "",
            OwnerId = _ownerId,
        });
        var author = Guid.NewGuid();

        var comment = await _service.AddCommentAsync(doc.Id, new CommentCreateRequest
        {
            AuthorId = author,
            Content = "Nice!",
        });
        Assert.NotNull(comment);
        Assert.Equal("Nice!", comment!.Content);

        var comments = await _service.ListCommentsAsync(doc.Id);
        Assert.Single(comments);

        Assert.True(await _service.DeleteCommentAsync(doc.Id, comment.Id));
        Assert.Empty(await _service.ListCommentsAsync(doc.Id));
    }

    [Fact]
    public async Task AddComment_ToNonexistentDocument_ReturnsNull()
    {
        var result = await _service.AddCommentAsync(Guid.NewGuid(), new CommentCreateRequest
        {
            AuthorId = Guid.NewGuid(),
            Content = "Orphan",
        });
        Assert.Null(result);
    }

    [Fact]
    public async Task Template_CRUD_AndCreateFrom()
    {
        var template = await _service.CreateTemplateAsync(new TemplateCreateRequest
        {
            Name = "Report",
            Description = "Monthly report",
            Content = "## Report\n\nContent here",
            CreatedBy = Guid.NewGuid(),
        });
        Assert.Equal("Report", template.Name);

        var templates = await _service.ListTemplatesAsync();
        Assert.Single(templates);

        var doc = await _service.CreateFromTemplateAsync(template.Id, new DocumentFromTemplateRequest
        {
            Title = "Jan Report",
            OwnerId = _ownerId,
        });
        Assert.NotNull(doc);
        Assert.Equal("Jan Report", doc!.Title);
        Assert.Equal("## Report\n\nContent here", doc.Content);
    }

    [Fact]
    public async Task CreateFromNonexistentTemplate_ReturnsNull()
    {
        var result = await _service.CreateFromTemplateAsync(Guid.NewGuid(), new DocumentFromTemplateRequest
        {
            Title = "Orphan",
            OwnerId = _ownerId,
        });
        Assert.Null(result);
    }

    [Fact]
    public void PaginateHelper()
    {
        Assert.Equal(2, _service.Paginate(10, 1, 5));
        Assert.Equal(3, _service.Paginate(11, 1, 5));
        Assert.Equal(1, _service.Paginate(0, 1, 5));
        Assert.Equal(1, _service.Paginate(10, 1, 0));
    }
}

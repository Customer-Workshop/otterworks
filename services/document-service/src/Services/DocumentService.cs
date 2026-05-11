using System.Web;
using Microsoft.EntityFrameworkCore;
using OtterWorks.DocumentService.Data;
using OtterWorks.DocumentService.DTOs;
using OtterWorks.DocumentService.Models;

namespace OtterWorks.DocumentService.Services;

public class DocumentService : IDocumentService
{
    private readonly DocumentDbContext _db;
    private readonly IEventPublisher _eventPublisher;
    private readonly ILogger<DocumentService> _logger;

    public DocumentService(DocumentDbContext db, IEventPublisher eventPublisher, ILogger<DocumentService> logger)
    {
        _db = db;
        _eventPublisher = eventPublisher;
        _logger = logger;
    }

    public async Task<DocumentResponse> CreateAsync(DocumentCreateRequest request)
    {
        var document = new Document
        {
            Title = request.Title,
            Content = request.Content,
            ContentType = request.ContentType,
            OwnerId = request.OwnerId ?? Guid.Empty,
            FolderId = request.FolderId,
            WordCount = WordCount(request.Content),
            Version = 1,
        };
        _db.Documents.Add(document);
        await _db.SaveChangesAsync();

        var version = new DocumentVersion
        {
            DocumentId = document.Id,
            VersionNumber = 1,
            Title = request.Title,
            Content = request.Content,
            CreatedBy = document.OwnerId,
        };
        _db.DocumentVersions.Add(version);
        await _db.SaveChangesAsync();

        await _eventPublisher.PublishAsync("document_created", BuildIndexPayload(document));
        return MapToResponse(document);
    }

    public async Task<DocumentResponse?> GetAsync(Guid documentId)
    {
        var document = await _db.Documents
            .FirstOrDefaultAsync(d => d.Id == documentId && !d.IsDeleted);
        return document is null ? null : MapToResponse(document);
    }

    public async Task<(List<DocumentResponse> Items, int Total)> ListAsync(
        Guid? ownerId, Guid? folderId, int page, int size)
    {
        var query = _db.Documents.Where(d => !d.IsDeleted && !d.IsTemplate);

        if (ownerId.HasValue)
        {
            query = query.Where(d => d.OwnerId == ownerId.Value);
        }

        if (folderId.HasValue)
        {
            query = query.Where(d => d.FolderId == folderId.Value);
        }

        var total = await query.CountAsync();
        var items = await query
            .OrderByDescending(d => d.UpdatedAt)
            .Skip((page - 1) * size)
            .Take(size)
            .ToListAsync();

        return (items.Select(MapToResponse).ToList(), total);
    }

    public async Task<DocumentResponse?> UpdateAsync(Guid documentId, DocumentUpdateRequest request, Guid? updatedBy = null)
    {
        var document = await _db.Documents
            .FirstOrDefaultAsync(d => d.Id == documentId && !d.IsDeleted);
        if (document is null)
        {
            return null;
        }

        document.Title = request.Title;
        document.Content = request.Content;
        document.ContentType = request.ContentType;
        document.FolderId = request.FolderId;
        document.WordCount = WordCount(request.Content);
        document.Version += 1;
        document.UpdatedAt = DateTime.UtcNow;

        var version = new DocumentVersion
        {
            DocumentId = document.Id,
            VersionNumber = document.Version,
            Title = request.Title,
            Content = request.Content,
            CreatedBy = updatedBy ?? document.OwnerId,
        };
        _db.DocumentVersions.Add(version);
        await _db.SaveChangesAsync();

        await _eventPublisher.PublishAsync("document_updated", BuildIndexPayload(document));
        return MapToResponse(document);
    }

    public async Task<DocumentResponse?> PatchAsync(Guid documentId, DocumentPatchRequest request)
    {
        var document = await _db.Documents
            .FirstOrDefaultAsync(d => d.Id == documentId && !d.IsDeleted);
        if (document is null)
        {
            return null;
        }

        var changed = false;
        if (request.ProvidedFields.Contains("title"))
        {
            document.Title = request.Title!;
            changed = true;
        }

        if (request.ProvidedFields.Contains("content"))
        {
            document.Content = request.Content!;
            document.WordCount = WordCount(request.Content);
            changed = true;
        }

        if (request.ProvidedFields.Contains("content_type"))
        {
            document.ContentType = request.ContentType!;
            changed = true;
        }

        if (request.ProvidedFields.Contains("folder_id"))
        {
            document.FolderId = request.FolderId;
            changed = true;
        }

        if (changed)
        {
            document.Version += 1;
            document.UpdatedAt = DateTime.UtcNow;

            var version = new DocumentVersion
            {
                DocumentId = document.Id,
                VersionNumber = document.Version,
                Title = document.Title,
                Content = document.Content,
                CreatedBy = document.OwnerId,
            };
            _db.DocumentVersions.Add(version);
        }

        await _db.SaveChangesAsync();

        if (changed)
        {
            await _eventPublisher.PublishAsync("document_updated", BuildIndexPayload(document));
        }

        return MapToResponse(document);
    }

    public async Task<bool> DeleteAsync(Guid documentId)
    {
        var document = await _db.Documents
            .FirstOrDefaultAsync(d => d.Id == documentId && !d.IsDeleted);
        if (document is null)
        {
            return false;
        }

        document.IsDeleted = true;
        await _db.SaveChangesAsync();

        await _eventPublisher.PublishAsync("document_deleted", new Dictionary<string, object>
        {
            ["id"] = documentId,
            ["type"] = "document",
        });
        return true;
    }

    public async Task<List<DocumentVersionResponse>> ListVersionsAsync(Guid documentId)
    {
        var versions = await _db.DocumentVersions
            .Where(v => v.DocumentId == documentId)
            .OrderByDescending(v => v.VersionNumber)
            .ToListAsync();

        return versions.Select(v => new DocumentVersionResponse
        {
            Id = v.Id,
            DocumentId = v.DocumentId,
            VersionNumber = v.VersionNumber,
            Title = v.Title,
            Content = v.Content,
            CreatedBy = v.CreatedBy,
            CreatedAt = v.CreatedAt,
        }).ToList();
    }

    public async Task<DocumentResponse?> RestoreVersionAsync(Guid documentId, Guid versionId)
    {
        var document = await _db.Documents
            .FirstOrDefaultAsync(d => d.Id == documentId && !d.IsDeleted);
        if (document is null)
        {
            return null;
        }

        var ver = await _db.DocumentVersions
            .FirstOrDefaultAsync(v => v.Id == versionId && v.DocumentId == documentId);
        if (ver is null)
        {
            return null;
        }

        document.Title = ver.Title;
        document.Content = ver.Content;
        document.WordCount = WordCount(ver.Content);
        document.Version += 1;
        document.UpdatedAt = DateTime.UtcNow;

        var newVer = new DocumentVersion
        {
            DocumentId = document.Id,
            VersionNumber = document.Version,
            Title = ver.Title,
            Content = ver.Content,
            CreatedBy = document.OwnerId,
        };
        _db.DocumentVersions.Add(newVer);
        await _db.SaveChangesAsync();

        var payload = BuildIndexPayload(document);
        payload["restored_from"] = versionId;
        await _eventPublisher.PublishAsync("document_updated", payload);
        return MapToResponse(document);
    }

    public async Task<(List<DocumentResponse> Items, int Total)> SearchAsync(string query, int page, int size)
    {
        var escaped = query.Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_");
        var pattern = $"%{escaped}%";

        var baseQuery = _db.Documents
            .Where(d => !d.IsDeleted && !d.IsTemplate)
            .Where(d => EF.Functions.ILike(d.Title, pattern) || EF.Functions.ILike(d.Content, pattern));

        var total = await baseQuery.CountAsync();
        var items = await baseQuery
            .OrderByDescending(d => d.UpdatedAt)
            .Skip((page - 1) * size)
            .Take(size)
            .ToListAsync();

        return (items.Select(MapToResponse).ToList(), total);
    }

    public (string Body, string ContentType) ExportDocument(DocumentResponse document, string format)
    {
        if (format == "html")
        {
            var safeTitle = HttpUtility.HtmlEncode(document.Title);
            var safeContent = HttpUtility.HtmlEncode(document.Content);
            var markup = $"<html><head><title>{safeTitle}</title></head>" +
                         $"<body><h1>{safeTitle}</h1>" +
                         $"<div>{safeContent}</div></body></html>";
            return (markup, "text/html");
        }

        if (format == "markdown")
        {
            var md = $"# {document.Title}\n\n{document.Content}";
            return (md, "text/markdown");
        }

        var text = $"TITLE: {document.Title}\n\n{document.Content}";
        return (text, "application/pdf");
    }

    public async Task<CommentResponse?> AddCommentAsync(Guid documentId, CommentCreateRequest request)
    {
        var document = await _db.Documents
            .FirstOrDefaultAsync(d => d.Id == documentId && !d.IsDeleted);
        if (document is null)
        {
            return null;
        }

        var comment = new Comment
        {
            DocumentId = documentId,
            AuthorId = request.AuthorId,
            Content = request.Content,
        };
        _db.Comments.Add(comment);
        await _db.SaveChangesAsync();

        await _eventPublisher.PublishAsync("comment_added", new Dictionary<string, object>
        {
            ["comment_id"] = comment.Id,
            ["document_id"] = documentId,
            ["author_id"] = request.AuthorId,
        });

        return MapCommentToResponse(comment);
    }

    public async Task<List<CommentResponse>> ListCommentsAsync(Guid documentId)
    {
        var comments = await _db.Comments
            .Where(c => c.DocumentId == documentId)
            .OrderBy(c => c.CreatedAt)
            .ToListAsync();

        return comments.Select(MapCommentToResponse).ToList();
    }

    public async Task<bool> DeleteCommentAsync(Guid documentId, Guid commentId)
    {
        var comment = await _db.Comments
            .FirstOrDefaultAsync(c => c.Id == commentId && c.DocumentId == documentId);
        if (comment is null)
        {
            return false;
        }

        _db.Comments.Remove(comment);
        await _db.SaveChangesAsync();
        return true;
    }

    public async Task<TemplateResponse> CreateTemplateAsync(TemplateCreateRequest request)
    {
        var template = new Template
        {
            Name = request.Name,
            Description = request.Description,
            Content = request.Content,
            ContentType = request.ContentType,
            CreatedBy = request.CreatedBy,
        };
        _db.Templates.Add(template);
        await _db.SaveChangesAsync();
        return MapTemplateToResponse(template);
    }

    public async Task<List<TemplateResponse>> ListTemplatesAsync()
    {
        var templates = await _db.Templates
            .OrderBy(t => t.Name)
            .ToListAsync();

        return templates.Select(MapTemplateToResponse).ToList();
    }

    public async Task<DocumentResponse?> CreateFromTemplateAsync(Guid templateId, DocumentFromTemplateRequest request)
    {
        var template = await _db.Templates.FirstOrDefaultAsync(t => t.Id == templateId);
        if (template is null)
        {
            return null;
        }

        var createRequest = new DocumentCreateRequest
        {
            Title = request.Title,
            Content = template.Content,
            ContentType = template.ContentType,
            OwnerId = request.OwnerId,
            FolderId = request.FolderId,
        };
        return await CreateAsync(createRequest);
    }

    public int Paginate(int total, int page, int size)
    {
        return size > 0 ? Math.Max(1, (int)Math.Ceiling((double)total / size)) : 1;
    }

    private static int WordCount(string? text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return 0;
        }

        return text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries).Length;
    }

    private static Dictionary<string, object> BuildIndexPayload(Document document)
    {
        return new Dictionary<string, object>
        {
            ["id"] = document.Id,
            ["title"] = document.Title,
            ["content"] = document.Content,
            ["owner_id"] = document.OwnerId,
            ["tags"] = Array.Empty<string>(),
            ["created_at"] = document.CreatedAt,
            ["updated_at"] = document.UpdatedAt,
        };
    }

    private static DocumentResponse MapToResponse(Document document)
    {
        return new DocumentResponse
        {
            Id = document.Id,
            Title = document.Title,
            Content = document.Content,
            ContentType = document.ContentType,
            OwnerId = document.OwnerId,
            FolderId = document.FolderId,
            IsDeleted = document.IsDeleted,
            IsTemplate = document.IsTemplate,
            WordCount = document.WordCount,
            Version = document.Version,
            CreatedAt = document.CreatedAt,
            UpdatedAt = document.UpdatedAt,
        };
    }

    private static CommentResponse MapCommentToResponse(Comment comment)
    {
        return new CommentResponse
        {
            Id = comment.Id,
            DocumentId = comment.DocumentId,
            AuthorId = comment.AuthorId,
            Content = comment.Content,
            CreatedAt = comment.CreatedAt,
            UpdatedAt = comment.UpdatedAt,
        };
    }

    private static TemplateResponse MapTemplateToResponse(Template template)
    {
        return new TemplateResponse
        {
            Id = template.Id,
            Name = template.Name,
            Description = template.Description,
            Content = template.Content,
            ContentType = template.ContentType,
            CreatedBy = template.CreatedBy,
            CreatedAt = template.CreatedAt,
            UpdatedAt = template.UpdatedAt,
        };
    }
}

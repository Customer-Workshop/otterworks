using OtterWorks.DocumentService.DTOs;

namespace OtterWorks.DocumentService.Services;

public interface IDocumentService
{
    Task<DocumentResponse> CreateAsync(DocumentCreateRequest request);

    Task<DocumentResponse?> GetAsync(Guid documentId);

    Task<(List<DocumentResponse> Items, int Total)> ListAsync(Guid? ownerId, Guid? folderId, int page, int size);

    Task<DocumentResponse?> UpdateAsync(Guid documentId, DocumentUpdateRequest request, Guid? updatedBy = null);

    Task<DocumentResponse?> PatchAsync(Guid documentId, DocumentPatchRequest request);

    Task<bool> DeleteAsync(Guid documentId);

    Task<List<DocumentVersionResponse>> ListVersionsAsync(Guid documentId);

    Task<DocumentResponse?> RestoreVersionAsync(Guid documentId, Guid versionId);

    Task<(List<DocumentResponse> Items, int Total)> SearchAsync(string query, int page, int size);

    (string Body, string ContentType) ExportDocument(DocumentResponse document, string format);

    Task<CommentResponse?> AddCommentAsync(Guid documentId, CommentCreateRequest request);

    Task<List<CommentResponse>> ListCommentsAsync(Guid documentId);

    Task<bool> DeleteCommentAsync(Guid documentId, Guid commentId);

    Task<TemplateResponse> CreateTemplateAsync(TemplateCreateRequest request);

    Task<List<TemplateResponse>> ListTemplatesAsync();

    Task<DocumentResponse?> CreateFromTemplateAsync(Guid templateId, DocumentFromTemplateRequest request);

    int Paginate(int total, int page, int size);
}

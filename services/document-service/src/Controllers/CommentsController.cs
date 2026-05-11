using Microsoft.AspNetCore.Mvc;
using OtterWorks.DocumentService.DTOs;
using OtterWorks.DocumentService.Services;

namespace OtterWorks.DocumentService.Controllers;

[ApiController]
[Route("api/v1/documents")]
public class CommentsController : ControllerBase
{
    private readonly IDocumentService _service;
    private readonly ILogger<CommentsController> _logger;

    public CommentsController(IDocumentService service, ILogger<CommentsController> logger)
    {
        _service = service;
        _logger = logger;
    }

    [HttpPost("{documentId}/comments")]
    public async Task<IActionResult> AddComment(Guid documentId, [FromBody] CommentCreateRequest body)
    {
        var comment = await _service.AddCommentAsync(documentId, body);
        if (comment is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        _logger.LogInformation("comment_added: {DocumentId} {CommentId}", documentId, comment.Id);
        return StatusCode(201, comment);
    }

    [HttpGet("{documentId}/comments")]
    public async Task<IActionResult> ListComments(Guid documentId)
    {
        var comments = await _service.ListCommentsAsync(documentId);
        return Ok(comments);
    }

    [HttpDelete("{documentId}/comments/{commentId}")]
    public async Task<IActionResult> DeleteComment(Guid documentId, Guid commentId)
    {
        var deleted = await _service.DeleteCommentAsync(documentId, commentId);
        if (!deleted)
        {
            return NotFound(new { detail = "Comment not found" });
        }

        _logger.LogInformation("comment_deleted: {DocumentId} {CommentId}", documentId, commentId);
        return NoContent();
    }
}

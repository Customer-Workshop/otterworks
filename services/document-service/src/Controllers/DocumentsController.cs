using System.IdentityModel.Tokens.Jwt;
using System.Text;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using OtterWorks.DocumentService.Config;
using OtterWorks.DocumentService.DTOs;
using OtterWorks.DocumentService.Services;

namespace OtterWorks.DocumentService.Controllers;

[ApiController]
[Route("api/v1/documents")]
public class DocumentsController : ControllerBase
{
    private readonly IDocumentService _service;
    private readonly JwtSettings _jwtSettings;
    private readonly ILogger<DocumentsController> _logger;

    public DocumentsController(
        IDocumentService service,
        IOptions<JwtSettings> jwtSettings,
        ILogger<DocumentsController> logger)
    {
        _service = service;
        _jwtSettings = jwtSettings.Value;
        _logger = logger;
    }

    [HttpPost("")]
    public async Task<IActionResult> CreateDocument([FromBody] DocumentCreateRequest body)
    {
        if (!body.OwnerId.HasValue || body.OwnerId == Guid.Empty)
        {
            var extractedId = ExtractUserId();
            if (extractedId is null)
            {
                return Unauthorized(new { detail = "owner_id is required: provide it in the body or authenticate via JWT" });
            }

            body.OwnerId = extractedId;
        }

        var document = await _service.CreateAsync(body);
        _logger.LogInformation("document_created: {DocumentId}", document.Id);
        return StatusCode(201, document);
    }

    [HttpGet("search")]
    public async Task<IActionResult> SearchDocuments(
        [FromQuery] string q,
        [FromQuery] int page = 1,
        [FromQuery] int size = 20)
    {
        var (items, total) = await _service.SearchAsync(q, page, size);
        return Ok(new DocumentListResponse
        {
            Items = items,
            Total = total,
            Page = page,
            Size = size,
            Pages = _service.Paginate(total, page, size),
        });
    }

    [HttpGet("")]
    public async Task<IActionResult> ListDocuments(
        [FromQuery(Name = "owner_id")] Guid? ownerId,
        [FromQuery(Name = "folder_id")] Guid? folderId,
        [FromQuery] int page = 1,
        [FromQuery] int size = 20)
    {
        var effectiveOwner = ownerId ?? ExtractUserId();
        var (items, total) = await _service.ListAsync(effectiveOwner, folderId, page, size);
        return Ok(new DocumentListResponse
        {
            Items = items,
            Total = total,
            Page = page,
            Size = size,
            Pages = _service.Paginate(total, page, size),
        });
    }

    [HttpGet("{documentId}")]
    public async Task<IActionResult> GetDocument(Guid documentId)
    {
        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var document = await _service.GetAsync(documentId);
        if (document is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        if (document.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        return Ok(document);
    }

    [HttpPut("{documentId}")]
    public async Task<IActionResult> UpdateDocument(Guid documentId, [FromBody] DocumentUpdateRequest body)
    {
        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var existing = await _service.GetAsync(documentId);
        if (existing is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        if (existing.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        var document = await _service.UpdateAsync(documentId, body);
        _logger.LogInformation("document_updated: {DocumentId}", documentId);
        return Ok(document);
    }

    [HttpPatch("{documentId}")]
    public async Task<IActionResult> PatchDocument(Guid documentId, [FromBody] System.Text.Json.JsonElement rawBody)
    {
        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var existing = await _service.GetAsync(documentId);
        if (existing is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        if (existing.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        var body = new DocumentPatchRequest();
        foreach (var property in rawBody.EnumerateObject())
        {
            body.ProvidedFields.Add(property.Name);
            switch (property.Name)
            {
                case "title":
                    body.Title = property.Value.GetString();
                    break;
                case "content":
                    body.Content = property.Value.GetString();
                    break;
                case "content_type":
                    body.ContentType = property.Value.GetString();
                    break;
                case "folder_id":
                    body.FolderId = property.Value.ValueKind == System.Text.Json.JsonValueKind.Null
                        ? null
                        : Guid.Parse(property.Value.GetString()!);
                    break;
            }
        }

        var document = await _service.PatchAsync(documentId, body);
        _logger.LogInformation("document_patched: {DocumentId}", documentId);
        return Ok(document);
    }

    [HttpDelete("{documentId}")]
    public async Task<IActionResult> DeleteDocument(Guid documentId)
    {
        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var existing = await _service.GetAsync(documentId);
        if (existing is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        if (existing.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        await _service.DeleteAsync(documentId);
        _logger.LogInformation("document_deleted: {DocumentId}", documentId);
        return NoContent();
    }

    [HttpGet("{documentId}/versions")]
    public async Task<IActionResult> ListVersions(Guid documentId)
    {
        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var document = await _service.GetAsync(documentId);
        if (document is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        if (document.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        var versions = await _service.ListVersionsAsync(documentId);
        return Ok(versions);
    }

    [HttpPost("{documentId}/versions/{versionId}/restore")]
    public async Task<IActionResult> RestoreVersion(Guid documentId, Guid versionId)
    {
        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var existing = await _service.GetAsync(documentId);
        if (existing is null)
        {
            return NotFound(new { detail = "Document or version not found" });
        }

        if (existing.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        var document = await _service.RestoreVersionAsync(documentId, versionId);
        if (document is null)
        {
            return NotFound(new { detail = "Document or version not found" });
        }

        _logger.LogInformation("document_version_restored: {DocumentId} {VersionId}", documentId, versionId);
        return Ok(document);
    }

    [HttpGet("{documentId}/export")]
    public async Task<IActionResult> ExportDocument(
        Guid documentId,
        [FromQuery] string format = "markdown")
    {
        if (format != "pdf" && format != "html" && format != "markdown")
        {
            return BadRequest(new { detail = "Invalid format" });
        }

        var userId = RequireUserId();
        if (userId is null)
        {
            return Unauthorized(new { detail = "Authentication required" });
        }

        var document = await _service.GetAsync(documentId);
        if (document is null)
        {
            return NotFound(new { detail = "Document not found" });
        }

        if (document.OwnerId != userId)
        {
            return StatusCode(403, new { detail = "Access denied" });
        }

        var (body, contentType) = _service.ExportDocument(document, format);
        return Content(body, contentType);
    }

    [HttpPost("from-template/{templateId}")]
    public async Task<IActionResult> CreateFromTemplate(Guid templateId, [FromBody] DocumentFromTemplateRequest body)
    {
        var document = await _service.CreateFromTemplateAsync(templateId, body);
        if (document is null)
        {
            return NotFound(new { detail = "Template not found" });
        }

        _logger.LogInformation("document_created_from_template: {DocumentId} {TemplateId}", document.Id, templateId);
        return StatusCode(201, document);
    }

    private Guid? ExtractUserId()
    {
        var authHeader = Request.Headers.Authorization.ToString();
        if (!string.IsNullOrEmpty(authHeader) && authHeader.StartsWith("Bearer ", StringComparison.Ordinal))
        {
            var token = authHeader["Bearer ".Length..];
            var secret = _jwtSettings.Secret;
            if (!string.IsNullOrEmpty(secret))
            {
                try
                {
                    var handler = new JwtSecurityTokenHandler();
                    handler.ValidateToken(token, new TokenValidationParameters
                    {
                        ValidateIssuerSigningKey = true,
                        IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret)),
                        ValidateIssuer = false,
                        ValidateAudience = false,
                        ValidateLifetime = false,
                        ValidAlgorithms = new[] { "HS256", "HS384" },
                    }, out var validatedToken);

                    var jwtToken = (JwtSecurityToken)validatedToken;
                    var userIdClaim = jwtToken.Claims.FirstOrDefault(c => c.Type == "user_id")
                        ?? jwtToken.Claims.FirstOrDefault(c => c.Type == "sub");
                    if (userIdClaim is not null && Guid.TryParse(userIdClaim.Value, out var userId))
                    {
                        return userId;
                    }
                }
                catch
                {
                    // Invalid token
                }
            }
        }

        return null;
    }

    private Guid? RequireUserId()
    {
        return ExtractUserId();
    }
}

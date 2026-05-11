using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using OtterWorks.FileService.Config;
using OtterWorks.FileService.Models;
using OtterWorks.FileService.Services;

namespace OtterWorks.FileService.Controllers;

public static class FileEndpoints
{
    public static void MapFileEndpoints(this WebApplication app)
    {
        var files = app.MapGroup("/api/v1/files");
        files.MapPost("/upload", UploadFile).DisableAntiforgery();
        files.MapGet("/shared", ListSharedFiles);
        files.MapGet("/trash", ListTrashed);
        files.MapGet("/activity", ListActivity);
        files.MapGet("", ListFiles);
        files.MapGet("/{fileId}", GetFileMetadata);
        files.MapDelete("/{fileId}", DeleteFile);
        files.MapGet("/{fileId}/download", DownloadFile);
        files.MapPut("/{fileId}/move", MoveFile);
        files.MapPatch("/{fileId}/rename", RenameFile);
        files.MapGet("/{fileId}/versions", ListVersions);
        files.MapPost("/{fileId}/trash", TrashFile);
        files.MapPost("/{fileId}/restore", RestoreFile);
        files.MapPost("/{fileId}/share", ShareFile);
        files.MapDelete("/{fileId}/share/{userId}", RemoveShare);

        var folders = app.MapGroup("/api/v1/folders");
        folders.MapGet("", ListFolders);
        folders.MapPost("", CreateFolder);
        folders.MapGet("/{folderId}", GetFolder);
        folders.MapPut("/{folderId}", UpdateFolder);
        folders.MapDelete("/{folderId}", DeleteFolder);
    }

    private static Guid? ResolveOwnerId(HttpContext context, Guid? queryOwnerId)
    {
        var headerValue = context.Request.Headers["X-User-ID"].FirstOrDefault();
        if (!string.IsNullOrEmpty(headerValue) && Guid.TryParse(headerValue.Trim(), out var headerOwnerId))
        {
            return headerOwnerId;
        }

        return queryOwnerId;
    }

    private static async Task<IResult> UploadFile(
        HttpRequest request,
        IS3StorageService s3,
        IMetadataService meta,
        IEventPublisher events,
        IOptions<AwsSettings> settings,
        ILogger<Program> logger)
    {
        var headerOwnerId = request.Headers["X-User-ID"].FirstOrDefault();
        Guid? headerOwner = null;
        if (!string.IsNullOrEmpty(headerOwnerId) && Guid.TryParse(headerOwnerId.Trim(), out var parsedHeaderOwner))
        {
            headerOwner = parsedHeaderOwner;
        }

        if (!request.HasFormContentType)
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = "Content type must be multipart/form-data" });
        }

        var form = await request.ReadFormAsync();
        var file = form.Files.GetFile("file");
        Guid? ownerId = null;
        Guid? folderId = null;

        if (form.TryGetValue("owner_id", out var ownerIdValue) && !string.IsNullOrWhiteSpace(ownerIdValue))
        {
            if (!Guid.TryParse(ownerIdValue.ToString().Trim(), out var parsedOwnerId))
            {
                return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid owner_id: {ownerIdValue}" });
            }

            ownerId = parsedOwnerId;
        }

        if (form.TryGetValue("folder_id", out var folderIdValue) && !string.IsNullOrWhiteSpace(folderIdValue))
        {
            if (!Guid.TryParse(folderIdValue.ToString().Trim(), out var parsedFolderId))
            {
                return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid folder_id: {folderIdValue}" });
            }

            folderId = parsedFolderId;
        }

        var owner = headerOwner ?? ownerId;
        if (!owner.HasValue)
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = "owner_id is required" });
        }

        if (file == null || file.Length == 0)
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = "file field is required" });
        }

        if (file.Length > settings.Value.MaxUploadBytes)
        {
            return Results.Json(
                new ErrorResponse { Error = "file_too_large", Message = $"File too large: max {settings.Value.MaxUploadBytes} bytes, got {file.Length} bytes" },
                statusCode: 413);
        }

        var fileId = Guid.NewGuid();
        var s3Key = $"files/{owner.Value}/{fileId}";
        var now = DateTime.UtcNow;
        var fileName = file.FileName ?? "unnamed";
        var contentType = file.ContentType ?? "application/octet-stream";

        using var stream = file.OpenReadStream();
        await s3.UploadObjectAsync(s3Key, stream, contentType);

        var fileMeta = new FileMetadata
        {
            Id = fileId,
            Name = fileName,
            MimeType = contentType,
            SizeBytes = file.Length,
            S3Key = s3Key,
            FolderId = folderId,
            OwnerId = owner.Value,
            Version = 1,
            IsTrashed = false,
            CreatedAt = now,
            UpdatedAt = now,
        };

        await meta.PutFileAsync(fileMeta);

        var version = new FileVersion
        {
            FileId = fileId,
            Version = 1,
            S3Key = s3Key,
            SizeBytes = file.Length,
            CreatedBy = owner.Value,
            CreatedAt = now,
        };
        await meta.PutVersionAsync(version);

        try
        {
            await events.FileUploadedAsync(fileId, owner.Value, folderId, fileName, contentType, file.Length);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_uploaded event");
        }

        logger.LogInformation("File uploaded: {FileId} {FileName} {Size}", fileId, fileName, file.Length);
        return Results.Created($"/api/v1/files/{fileId}", new UploadResponse { File = fileMeta });
    }

    private static async Task<IResult> GetFileMetadata(
        string fileId,
        IMetadataService meta)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.GetFileAsync(id);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        var shares = await meta.ListSharesAsync(id);
        var response = new FileDetailResponse
        {
            Id = file.Id,
            Name = file.Name,
            MimeType = file.MimeType,
            SizeBytes = file.SizeBytes,
            S3Key = file.S3Key,
            FolderId = file.FolderId,
            OwnerId = file.OwnerId,
            Version = file.Version,
            IsTrashed = file.IsTrashed,
            CreatedAt = file.CreatedAt,
            UpdatedAt = file.UpdatedAt,
            SharedWith = shares,
        };

        return Results.Ok(response);
    }

    private static async Task<IResult> ListFiles(
        HttpContext context,
        IMetadataService meta,
        [FromQuery(Name = "folder_id")] Guid? folderId,
        [FromQuery(Name = "owner_id")] Guid? queryOwnerId,
        [FromQuery] int? page,
        [FromQuery] int? page_size,
        [FromQuery] bool? include_trashed)
    {
        var includeTrashed = include_trashed ?? false;
        var ownerId = ResolveOwnerId(context, queryOwnerId);
        var files = await meta.ListFilesAsync(folderId, ownerId, includeTrashed);

        var currentPage = Math.Max(page ?? 1, 1);
        var pageSize = Math.Min(page_size ?? 50, 100);
        var total = files.Count;
        var start = (currentPage - 1) * pageSize;
        var paged = files.Skip(start).Take(pageSize).ToList();

        return Results.Ok(new ListFilesResponse
        {
            Files = paged,
            Total = total,
            Page = currentPage,
            PageSize = pageSize,
        });
    }

    private static async Task<IResult> ListSharedFiles(
        HttpContext context,
        IMetadataService meta,
        [FromQuery] int? page,
        [FromQuery] int? page_size)
    {
        var userIdHeader = context.Request.Headers["X-User-ID"].FirstOrDefault();
        if (string.IsNullOrEmpty(userIdHeader) || !Guid.TryParse(userIdHeader, out var userId))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = "missing X-User-ID header" });
        }

        var shares = await meta.ListSharesForUserAsync(userId);

        var seenFileIds = new HashSet<Guid>();
        var files = new List<FileMetadata>();
        foreach (var share in shares)
        {
            if (!seenFileIds.Add(share.FileId))
            {
                continue;
            }

            var file = await meta.GetFileAsync(share.FileId);
            if (file != null && !file.IsTrashed)
            {
                files.Add(file);
            }
        }

        var currentPage = Math.Max(page ?? 1, 1);
        var pageSize = Math.Min(page_size ?? 50, 100);
        var total = files.Count;
        var start = (currentPage - 1) * pageSize;
        var paged = files.Skip(start).Take(pageSize).ToList();

        return Results.Ok(new ListFilesResponse
        {
            Files = paged,
            Total = total,
            Page = currentPage,
            PageSize = pageSize,
        });
    }

    private static async Task<IResult> ListTrashed(
        HttpContext context,
        IMetadataService meta,
        [FromQuery(Name = "owner_id")] Guid? queryOwnerId,
        [FromQuery] int? page,
        [FromQuery] int? page_size)
    {
        var ownerId = ResolveOwnerId(context, queryOwnerId);
        var files = await meta.ListTrashedAsync(ownerId);

        var currentPage = Math.Max(page ?? 1, 1);
        var pageSize = Math.Min(page_size ?? 50, 100);
        var total = files.Count;
        var start = (currentPage - 1) * pageSize;
        var paged = files.Skip(start).Take(pageSize).ToList();

        return Results.Ok(new ListFilesResponse
        {
            Files = paged,
            Total = total,
            Page = currentPage,
            PageSize = pageSize,
        });
    }

    private static async Task<IResult> DeleteFile(
        string fileId,
        IS3StorageService s3,
        IMetadataService meta,
        IEventPublisher events,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.GetFileAsync(id);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        await meta.DeleteFileAsync(id);
        await s3.DeleteObjectAsync(file.S3Key);

        try
        {
            await events.FileDeletedAsync(id, file.OwnerId);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_deleted event");
        }

        logger.LogInformation("File deleted: {FileId}", fileId);
        return Results.NoContent();
    }

    private static async Task<IResult> DownloadFile(
        string fileId,
        IS3StorageService s3,
        IMetadataService meta)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.GetFileAsync(id);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        var url = await s3.GetPresignedDownloadUrlAsync(file.S3Key, 3600);
        return Results.Ok(new DownloadResponse { Url = url, ExpiresInSecs = 3600 });
    }

    private static async Task<IResult> MoveFile(
        string fileId,
        [FromBody] MoveFileRequest body,
        IMetadataService meta,
        IEventPublisher events,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.MoveFileAsync(id, body.FolderId);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        try
        {
            await events.FileMovedAsync(id, file.OwnerId, body.FolderId);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_moved event");
        }

        logger.LogInformation("File moved: {FileId} to folder {FolderId}", fileId, body.FolderId);
        return Results.Ok(file);
    }

    private static async Task<IResult> RenameFile(
        string fileId,
        [FromBody] RenameFileRequest body,
        IMetadataService meta,
        IEventPublisher events,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var name = body.Name.Trim();
        if (string.IsNullOrEmpty(name))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = "name cannot be empty" });
        }

        var file = await meta.RenameFileAsync(id, name);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        try
        {
            await events.FileUpdatedAsync(id, file.OwnerId, file.FolderId, file.Name, file.MimeType, file.SizeBytes);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_updated event");
        }

        logger.LogInformation("File renamed: {FileId} to {Name}", fileId, name);
        return Results.Ok(file);
    }

    private static async Task<IResult> ListVersions(
        string fileId,
        IMetadataService meta)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var versions = await meta.ListVersionsAsync(id);
        return Results.Ok(new ListVersionsResponse { Versions = versions });
    }

    private static async Task<IResult> TrashFile(
        string fileId,
        IMetadataService meta,
        IEventPublisher events,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.TrashFileAsync(id);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        try
        {
            await events.FileTrashedAsync(id, file.OwnerId);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_trashed event");
        }

        logger.LogInformation("File trashed: {FileId}", fileId);
        return Results.Ok(file);
    }

    private static async Task<IResult> RestoreFile(
        string fileId,
        IMetadataService meta,
        IEventPublisher events,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.RestoreFileAsync(id);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        try
        {
            await events.FileRestoredAsync(id, file.OwnerId, file.FolderId, file.Name, file.MimeType, file.SizeBytes);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_restored event");
        }

        logger.LogInformation("File restored: {FileId}", fileId);
        return Results.Ok(file);
    }

    private static async Task<IResult> ShareFile(
        string fileId,
        [FromBody] ShareFileRequest body,
        IMetadataService meta,
        IEventPublisher events,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        var file = await meta.GetFileAsync(id);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        var existing = await meta.FindExistingShareAsync(id, body.SharedWith);
        if (existing != null)
        {
            if (existing.Permission != body.Permission)
            {
                var updated = new FileShare
                {
                    Id = existing.Id,
                    FileId = id,
                    SharedWith = body.SharedWith,
                    Permission = body.Permission,
                    SharedBy = body.SharedBy,
                    CreatedAt = existing.CreatedAt,
                };
                await meta.PutShareAsync(updated);
                logger.LogInformation("File share updated: {FileId} shared with {SharedWith}", fileId, body.SharedWith);
                return Results.Ok(new ShareFileResponse { Share = updated });
            }

            logger.LogInformation("File already shared: {FileId} with {SharedWith}", fileId, body.SharedWith);
            return Results.Ok(new ShareFileResponse { Share = existing });
        }

        var share = new FileShare
        {
            Id = Guid.NewGuid(),
            FileId = id,
            SharedWith = body.SharedWith,
            Permission = body.Permission,
            SharedBy = body.SharedBy,
            CreatedAt = DateTime.UtcNow,
        };

        await meta.PutShareAsync(share);

        try
        {
            await events.FileSharedAsync(id, file.OwnerId, body.SharedWith);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to publish file_shared event");
        }

        logger.LogInformation("File shared: {FileId} with {SharedWith}", fileId, body.SharedWith);
        return Results.Created($"/api/v1/files/{fileId}/share", new ShareFileResponse { Share = share });
    }

    private static async Task<IResult> RemoveShare(
        string fileId,
        string userId,
        IMetadataService meta,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(fileId, out var fid))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid file id: {fileId}" });
        }

        if (!Guid.TryParse(userId, out var uid))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid user id: {userId}" });
        }

        var file = await meta.GetFileAsync(fid);
        if (file == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "file_not_found", Message = $"File not found: {fileId}" });
        }

        var share = await meta.FindExistingShareAsync(fid, uid);
        if (share == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "share_not_found", Message = "Share not found" });
        }

        await meta.DeleteShareAsync(share.Id);
        logger.LogInformation("File share removed: {FileId} user {UserId}", fileId, userId);
        return Results.NoContent();
    }

    // -- Folder Endpoints --

    private static async Task<IResult> ListFolders(
        HttpContext context,
        IMetadataService meta,
        [FromQuery(Name = "parent_id")] Guid? parentId,
        [FromQuery(Name = "owner_id")] Guid? queryOwnerId)
    {
        var ownerId = ResolveOwnerId(context, queryOwnerId);
        var folders = await meta.ListFoldersAsync(parentId, ownerId);
        return Results.Ok(new ListFoldersResponse { Folders = folders });
    }

    private static async Task<IResult> CreateFolder(
        [FromBody] CreateFolderRequest body,
        IMetadataService meta,
        ILogger<Program> logger)
    {
        var now = DateTime.UtcNow;
        var folder = new Folder
        {
            Id = Guid.NewGuid(),
            Name = body.Name,
            ParentId = body.ParentId,
            OwnerId = body.OwnerId,
            CreatedAt = now,
            UpdatedAt = now,
        };

        await meta.PutFolderAsync(folder);
        logger.LogInformation("Folder created: {FolderId} {Name}", folder.Id, folder.Name);
        return Results.Created($"/api/v1/folders/{folder.Id}", folder);
    }

    private static async Task<IResult> GetFolder(
        string folderId,
        IMetadataService meta)
    {
        if (!Guid.TryParse(folderId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid folder id: {folderId}" });
        }

        var folder = await meta.GetFolderAsync(id);
        if (folder == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "folder_not_found", Message = $"Folder not found: {folderId}" });
        }

        return Results.Ok(folder);
    }

    private static async Task<IResult> UpdateFolder(
        string folderId,
        [FromBody] UpdateFolderRequest body,
        IMetadataService meta)
    {
        if (!Guid.TryParse(folderId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid folder id: {folderId}" });
        }

        var folder = await meta.UpdateFolderAsync(id, body.Name, body.ParentId);
        if (folder == null)
        {
            return Results.NotFound(new ErrorResponse { Error = "folder_not_found", Message = $"Folder not found: {folderId}" });
        }

        return Results.Ok(folder);
    }

    private static async Task<IResult> DeleteFolder(
        string folderId,
        IMetadataService meta,
        ILogger<Program> logger)
    {
        if (!Guid.TryParse(folderId, out var id))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = $"invalid folder id: {folderId}" });
        }

        await meta.DeleteFolderAsync(id);
        logger.LogInformation("Folder deleted: {FolderId}", folderId);
        return Results.NoContent();
    }

    // -- Activity Endpoint --

    private static async Task<IResult> ListActivity(
        HttpContext context,
        IMetadataService meta,
        [FromQuery] int? limit)
    {
        var userIdHeader = context.Request.Headers["X-User-ID"].FirstOrDefault();
        if (string.IsNullOrEmpty(userIdHeader) || !Guid.TryParse(userIdHeader.Trim(), out var ownerId))
        {
            return Results.BadRequest(new ErrorResponse { Error = "bad_request", Message = "missing owner context" });
        }

        var actualLimit = Math.Min(limit ?? 20, 50);

        var filesTask = meta.ListFilesAsync(null, ownerId, true);
        var sharesTask = meta.ListSharesByOwnerAsync(ownerId);
        await Task.WhenAll(filesTask, sharesTask);

        var files = filesTask.Result;
        var shares = sharesTask.Result;

        var fileNames = files.ToDictionary(f => f.Id, f => f.Name);
        var items = new List<ActivityItem>();

        foreach (var f in files)
        {
            items.Add(new ActivityItem
            {
                Id = $"upload-{f.Id}",
                Type = "upload",
                Description = $"Uploaded {f.Name}",
                ActorName = "You",
                ResourceName = f.Name,
                ResourceType = "file",
                ResourceId = f.Id.ToString(),
                CreatedAt = f.CreatedAt.ToString("o"),
            });
        }

        foreach (var s in shares)
        {
            var name = fileNames.TryGetValue(s.FileId, out var n) ? n : "a file";
            items.Add(new ActivityItem
            {
                Id = $"share-{s.Id}",
                Type = "share",
                Description = $"Shared {name}",
                ActorName = "You",
                ResourceName = name,
                ResourceType = "file",
                ResourceId = s.FileId.ToString(),
                CreatedAt = s.CreatedAt.ToString("o"),
            });
        }

        items.Sort((a, b) => string.Compare(b.CreatedAt, a.CreatedAt, StringComparison.Ordinal));
        if (items.Count > actualLimit)
        {
            items = items.Take(actualLimit).ToList();
        }

        return Results.Ok(new ActivityResponse { Items = items });
    }
}

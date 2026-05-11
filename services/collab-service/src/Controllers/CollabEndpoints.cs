using Microsoft.AspNetCore.Mvc;
using OtterWorks.CollabService.Models;
using OtterWorks.CollabService.Services;

namespace OtterWorks.CollabService.Controllers;

public static class CollabEndpoints
{
    public static void MapCollabEndpoints(this WebApplication app)
    {
        app.MapGet("/api/v1/collab/documents/{id}/presence", (
            string id,
            IAwarenessService awareness) =>
        {
            List<UserAwareness> users = awareness.GetDocumentUsers(id);
            return Results.Ok(new PresenceInfo
            {
                DocumentId = id,
                Users = users,
                Count = users.Count,
            });
        });

        app.MapGet("/api/v1/collab/documents", (IAwarenessService awareness) =>
        {
            List<string> documentIds = awareness.GetActiveDocumentIds();
            var documents = documentIds.Select(id => new
            {
                documentId = id,
                userCount = awareness.GetDocumentUserCount(id),
            }).ToList();
            return Results.Ok(new { documents, count = documents.Count });
        });

        app.MapGet("/api/v1/collab/documents/{id}/meta", async (
            string id,
            IDocumentStore documentStore) =>
        {
            DocumentMeta? meta = await documentStore.GetDocumentMetaAsync(id);
            return meta is not null ? Results.Ok(meta) : Results.NotFound();
        });

        app.MapGet("/api/v1/collab/documents/{id}/snapshots", async (
            string id,
            [FromQuery] int? limit,
            IDocumentStore documentStore) =>
        {
            List<DocumentSnapshot> snapshots = await documentStore.GetSnapshotsAsync(id, limit ?? 20);
            return Results.Ok(new { documentId = id, snapshots });
        });
    }
}

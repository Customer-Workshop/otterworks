using OtterWorks.NotificationService.Models;
using OtterWorks.NotificationService.Services;

namespace OtterWorks.NotificationService.Controllers;

public static class NotificationEndpoints
{
    public static void MapNotificationEndpoints(this WebApplication app)
    {
        var notifications = app.MapGroup("/api/v1/notifications");

        notifications.MapGet("/", async (HttpContext context, INotificationService service) =>
        {
            var userId = context.Request.Headers["X-User-ID"].FirstOrDefault()
                ?? context.Request.Query["user_id"].FirstOrDefault();

            if (string.IsNullOrWhiteSpace(userId))
            {
                return Results.BadRequest(new ErrorResponse { Error = "user_id is required (via X-User-ID header or query parameter)" });
            }

            var page = int.TryParse(context.Request.Query["page"], out var p) ? p : 1;
            var pageSize = int.TryParse(context.Request.Query["page_size"], out var ps) ? ps : 20;

            var (items, total) = await service.GetNotificationsAsync(userId, page, pageSize);

            return Results.Ok(new PaginatedResponse<Notification>
            {
                Data = items,
                Total = total,
                Page = page,
                PageSize = pageSize,
                HasMore = (page * pageSize) < total,
            });
        });

        notifications.MapGet("/unread-count", async (HttpContext context, INotificationService service) =>
        {
            var userId = context.Request.Headers["X-User-ID"].FirstOrDefault()
                ?? context.Request.Query["user_id"].FirstOrDefault();

            if (string.IsNullOrWhiteSpace(userId))
            {
                return Results.BadRequest(new ErrorResponse { Error = "user_id is required (via X-User-ID header or query parameter)" });
            }

            var count = await service.GetUnreadCountAsync(userId);
            return Results.Ok(new UnreadCountResponse { UserId = userId, UnreadCount = count });
        });

        notifications.MapGet("/{id}", async (string id, INotificationService service) =>
        {
            var notification = await service.GetNotificationByIdAsync(id);
            return notification is not null
                ? Results.Ok(notification)
                : Results.NotFound(new ErrorResponse { Error = "Notification not found" });
        });

        notifications.MapPut("/{id}/read", async (string id, INotificationService service) =>
        {
            var success = await service.MarkAsReadAsync(id);
            return success
                ? Results.NoContent()
                : Results.NotFound(new ErrorResponse { Error = "Notification not found" });
        });

        notifications.MapPut("/read-all", async (HttpContext context, INotificationService service) =>
        {
            var userId = context.Request.Headers["X-User-ID"].FirstOrDefault()
                ?? context.Request.Query["user_id"].FirstOrDefault();

            if (string.IsNullOrWhiteSpace(userId))
            {
                return Results.BadRequest(new ErrorResponse { Error = "user_id is required (via X-User-ID header or query parameter)" });
            }

            var count = await service.MarkAllAsReadAsync(userId);
            return Results.Ok(new MarkAllReadResponse { MarkedCount = count });
        });

        notifications.MapDelete("/{id}", async (string id, INotificationService service) =>
        {
            var success = await service.DeleteNotificationAsync(id);
            return success
                ? Results.NoContent()
                : Results.NotFound(new ErrorResponse { Error = "Notification not found" });
        });

        var preferences = app.MapGroup("/api/v1/preferences");

        preferences.MapGet("/", async (HttpContext context, INotificationService service) =>
        {
            var userId = context.Request.Headers["X-User-ID"].FirstOrDefault()
                ?? context.Request.Query["user_id"].FirstOrDefault();

            if (string.IsNullOrWhiteSpace(userId))
            {
                return Results.BadRequest(new ErrorResponse { Error = "user_id is required (via X-User-ID header or query parameter)" });
            }

            var prefs = await service.GetPreferencesAsync(userId);
            return Results.Ok(prefs);
        });

        preferences.MapPut("/", async (NotificationPreferenceRequest request, INotificationService service) =>
        {
            await service.UpdatePreferencesAsync(request.UserId, request.EventType, request.Channels);
            return Results.NoContent();
        });
    }
}

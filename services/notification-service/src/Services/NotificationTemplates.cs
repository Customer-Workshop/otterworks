using OtterWorks.NotificationService.Models;

namespace OtterWorks.NotificationService.Services;

public class RenderedNotification
{
    public string Title { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public string EmailSubject { get; set; } = string.Empty;
    public string EmailBody { get; set; } = string.Empty;
}

public static class NotificationTemplates
{
    private sealed record Template(string TitleTemplate, string MessageTemplate, string EmailSubjectTemplate, string EmailBodyTemplate);

    private static readonly Dictionary<string, Template> Templates = new()
    {
        ["file_shared"] = new Template(
            TitleTemplate: "File Shared With You",
            MessageTemplate: "A file has been shared with you by user {{actorId}}.",
            EmailSubjectTemplate: "OtterWorks: A file has been shared with you",
            EmailBodyTemplate: @"<html>
<body>
    <h2>File Shared</h2>
    <p>A file (ID: {{fileId}}) has been shared with you by user {{actorId}}.</p>
    <p>Log in to OtterWorks to view the file.</p>
    <br/>
    <p style=""color: #888;"">— OtterWorks Notification Service</p>
</body>
</html>"),
        ["comment_added"] = new Template(
            TitleTemplate: "New Comment",
            MessageTemplate: "A new comment was added by user {{actorId}} on document {{documentId}}.",
            EmailSubjectTemplate: "OtterWorks: New comment on your document",
            EmailBodyTemplate: @"<html>
<body>
    <h2>New Comment</h2>
    <p>User {{actorId}} added a comment on document {{documentId}}.</p>
    <p>Log in to OtterWorks to view the comment.</p>
    <br/>
    <p style=""color: #888;"">— OtterWorks Notification Service</p>
</body>
</html>"),
        ["document_edited"] = new Template(
            TitleTemplate: "Document Edited",
            MessageTemplate: "Document {{documentId}} was edited by user {{actorId}}.",
            EmailSubjectTemplate: "OtterWorks: A document you follow was edited",
            EmailBodyTemplate: @"<html>
<body>
    <h2>Document Edited</h2>
    <p>Document {{documentId}} was edited by user {{actorId}}.</p>
    <p>Log in to OtterWorks to view the changes.</p>
    <br/>
    <p style=""color: #888;"">— OtterWorks Notification Service</p>
</body>
</html>"),
        ["user_mentioned"] = new Template(
            TitleTemplate: "You Were Mentioned",
            MessageTemplate: "You were mentioned by user {{actorId}} in document {{documentId}}.",
            EmailSubjectTemplate: "OtterWorks: You were mentioned in a document",
            EmailBodyTemplate: @"<html>
<body>
    <h2>You Were Mentioned</h2>
    <p>User {{actorId}} mentioned you in document {{documentId}}.</p>
    <p>Log in to OtterWorks to see the context.</p>
    <br/>
    <p style=""color: #888;"">— OtterWorks Notification Service</p>
</body>
</html>"),
    };

    public static RenderedNotification Render(SqsNotificationMessage sqsEvent)
    {
        if (!Templates.TryGetValue(sqsEvent.EventType, out var template))
        {
            return new RenderedNotification
            {
                Title = "Notification",
                Message = "You have a new notification.",
                EmailSubject = "OtterWorks: New notification",
                EmailBody = "<html><body><p>You have a new notification.</p></body></html>",
            };
        }

        var actorId = string.IsNullOrEmpty(sqsEvent.ActorId) ? sqsEvent.OwnerId : sqsEvent.ActorId;

        var variables = new Dictionary<string, string>
        {
            ["actorId"] = actorId,
            ["fileId"] = sqsEvent.FileId,
            ["documentId"] = sqsEvent.DocumentId,
            ["commentId"] = sqsEvent.CommentId,
            ["userId"] = sqsEvent.UserId,
        };

        return new RenderedNotification
        {
            Title = ReplaceVariables(template.TitleTemplate, variables),
            Message = ReplaceVariables(template.MessageTemplate, variables),
            EmailSubject = ReplaceVariables(template.EmailSubjectTemplate, variables),
            EmailBody = ReplaceVariables(template.EmailBodyTemplate, variables),
        };
    }

    private static string ReplaceVariables(string template, Dictionary<string, string> variables)
    {
        var result = template;
        foreach (var (key, value) in variables)
        {
            result = result.Replace("{{" + key + "}}", value, StringComparison.Ordinal);
        }

        return result;
    }
}

namespace OtterWorks.CollabService.Models;

public class UserAwareness
{
    public string UserId { get; set; } = string.Empty;

    public string DisplayName { get; set; } = string.Empty;

    public string Email { get; set; } = string.Empty;

    public string Color { get; set; } = string.Empty;

    public CursorPosition? Cursor { get; set; }

    public CursorPosition? Selection { get; set; }

    public bool IsTyping { get; set; }

    public long LastActive { get; set; }
}

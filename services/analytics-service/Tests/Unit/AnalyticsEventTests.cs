using OtterWorks.AnalyticsService.Models;

namespace AnalyticsService.Tests.Unit;

public class AnalyticsEventTests
{
    [Fact]
    public void Create_ShouldGenerateUniqueEventIdAndTimestamp()
    {
        var analyticsEvent = AnalyticsEvent.Create(
            EventTypes.DocumentCreated,
            "user-1",
            "doc-1",
            "document");

        Assert.NotEmpty(analyticsEvent.EventId);
        Assert.Equal(EventTypes.DocumentCreated, analyticsEvent.EventType);
        Assert.Equal("user-1", analyticsEvent.UserId);
        Assert.Equal("doc-1", analyticsEvent.ResourceId);
        Assert.Equal("document", analyticsEvent.ResourceType);
        Assert.Empty(analyticsEvent.Metadata);
        Assert.True(analyticsEvent.Timestamp <= DateTime.UtcNow);
    }

    [Fact]
    public void Create_ShouldIncludeMetadataWhenProvided()
    {
        var meta = new Dictionary<string, string> { ["title"] = "My Doc", ["size"] = "1024" };
        var analyticsEvent = AnalyticsEvent.Create(
            EventTypes.FileUploaded,
            "user-2",
            "file-1",
            "file",
            meta);

        Assert.Equal(meta, analyticsEvent.Metadata);
    }

    [Fact]
    public void EventTypes_ShouldContainAllExpectedTypes()
    {
        Assert.Contains(EventTypes.DocumentCreated, EventTypes.All);
        Assert.Contains(EventTypes.FileUploaded, EventTypes.All);
        Assert.Contains(EventTypes.UserLoggedIn, EventTypes.All);
        Assert.Contains(EventTypes.CollabSessionStarted, EventTypes.All);
        Assert.Contains(EventTypes.StorageAllocated, EventTypes.All);
        Assert.Equal(15, EventTypes.All.Count);
    }
}

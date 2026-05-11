using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Tests.Unit.Models;

public class AnnouncementTests
{
    [Fact]
    public void Active_ReturnsTrueWhenPublishedAndInDateRange()
    {
        var announcement = new Announcement
        {
            Status = "published",
            StartsAt = DateTime.UtcNow.AddDays(-1),
            EndsAt = DateTime.UtcNow.AddDays(7),
        };

        Assert.True(announcement.Active);
    }

    [Fact]
    public void Active_ReturnsFalseWhenDraft()
    {
        var announcement = new Announcement { Status = "draft" };

        Assert.False(announcement.Active);
    }

    [Fact]
    public void Active_ReturnsFalseWhenExpired()
    {
        var announcement = new Announcement
        {
            Status = "published",
            StartsAt = DateTime.UtcNow.AddDays(-14),
            EndsAt = DateTime.UtcNow.AddDays(-1),
        };

        Assert.False(announcement.Active);
    }

    [Fact]
    public void Active_ReturnsTrueWhenNoDateConstraints()
    {
        var announcement = new Announcement { Status = "published" };

        Assert.True(announcement.Active);
    }

    [Fact]
    public void ValidSeverities_ContainsExpectedValues()
    {
        Assert.Contains("info", Announcement.ValidSeverities);
        Assert.Contains("warning", Announcement.ValidSeverities);
        Assert.Contains("critical", Announcement.ValidSeverities);
        Assert.Contains("maintenance", Announcement.ValidSeverities);
    }

    [Fact]
    public void ValidStatuses_ContainsExpectedValues()
    {
        Assert.Contains("draft", Announcement.ValidStatuses);
        Assert.Contains("published", Announcement.ValidStatuses);
        Assert.Contains("archived", Announcement.ValidStatuses);
    }
}

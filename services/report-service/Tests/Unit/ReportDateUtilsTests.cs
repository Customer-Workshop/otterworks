using FluentAssertions;
using OtterWorks.ReportService.Utilities;

namespace OtterWorks.ReportService.Tests.Unit;

public class ReportDateUtilsTests
{
    [Fact]
    public void ToIsoString_FormatsCorrectlyAsUtc()
    {
        var date = new DateTime(2024, 3, 15, 10, 30, 45, DateTimeKind.Utc);
        var result = ReportDateUtils.ToIsoString(date);
        result.Should().Be("2024-03-15T10:30:45Z");
    }

    [Fact]
    public void ToIsoString_ReturnsNullForNullInput()
    {
        var result = ReportDateUtils.ToIsoString(null);
        result.Should().BeNull();
    }

    [Fact]
    public void ToDisplayString_FormatsCorrectly()
    {
        var date = new DateTime(2024, 3, 15, 10, 30, 0, DateTimeKind.Utc);
        var result = ReportDateUtils.ToDisplayString(date);
        result.Should().Be("Mar 15, 2024 10:30");
    }

    [Fact]
    public void ToDisplayString_ReturnsNA_ForNull()
    {
        var result = ReportDateUtils.ToDisplayString(null);
        result.Should().Be("N/A");
    }

    [Fact]
    public void ToFileNameString_FormatsCorrectly()
    {
        var date = new DateTime(2024, 3, 15, 10, 30, 45, DateTimeKind.Utc);
        var result = ReportDateUtils.ToFileNameString(date);
        result.Should().Be("20240315_103045");
    }

    [Fact]
    public void ParseIsoDate_ParsesMultipleFormats()
    {
        var result1 = ReportDateUtils.ParseIsoDate("2024-03-15T10:30:45Z");
        result1.Year.Should().Be(2024);
        result1.Month.Should().Be(3);
        result1.Day.Should().Be(15);

        var result2 = ReportDateUtils.ParseIsoDate("2024-03-15 10:30:45");
        result2.Year.Should().Be(2024);

        var result3 = ReportDateUtils.ParseIsoDate("2024-03-15");
        result3.Year.Should().Be(2024);
    }

    [Fact]
    public void ParseIsoDate_ThrowsOnInvalidInput()
    {
        Action act = () => ReportDateUtils.ParseIsoDate("not-a-date");
        act.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void DaysAgo_ReturnsDateNDaysInPast()
    {
        var result = ReportDateUtils.DaysAgo(7);
        var expected = DateTime.UtcNow.AddDays(-7);
        result.Should().BeCloseTo(expected, TimeSpan.FromSeconds(2));
    }

    [Fact]
    public void StartOfToday_ReturnsMidnightUtc()
    {
        var result = ReportDateUtils.StartOfToday();
        result.Hour.Should().Be(0);
        result.Minute.Should().Be(0);
        result.Second.Should().Be(0);
        result.Date.Should().Be(DateTime.UtcNow.Date);
    }

    [Fact]
    public void StartOfMonth_ReturnsFirstDayOfMonthMidnightUtc()
    {
        var result = ReportDateUtils.StartOfMonth();
        result.Day.Should().Be(1);
        result.Hour.Should().Be(0);
        result.Minute.Should().Be(0);
        result.Second.Should().Be(0);
        result.Month.Should().Be(DateTime.UtcNow.Month);
    }

    [Fact]
    public void IsWithinRange_ReturnsTrueForDateInsideRange()
    {
        var start = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        var end = new DateTime(2024, 12, 31, 0, 0, 0, DateTimeKind.Utc);
        var date = new DateTime(2024, 6, 15, 0, 0, 0, DateTimeKind.Utc);

        ReportDateUtils.IsWithinRange(date, start, end).Should().BeTrue();
    }

    [Fact]
    public void IsWithinRange_ReturnsFalseForDateOutsideRange()
    {
        var start = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        var end = new DateTime(2024, 12, 31, 0, 0, 0, DateTimeKind.Utc);
        var date = new DateTime(2025, 6, 15, 0, 0, 0, DateTimeKind.Utc);

        ReportDateUtils.IsWithinRange(date, start, end).Should().BeFalse();
    }

    [Fact]
    public void HumanReadableDuration_ReturnsSecondsForShortDurations()
    {
        var start = new DateTime(2024, 1, 1, 10, 0, 0, DateTimeKind.Utc);
        var end = new DateTime(2024, 1, 1, 10, 0, 30, DateTimeKind.Utc);

        var result = ReportDateUtils.HumanReadableDuration(start, end);
        result.Should().Be("30s");
    }

    [Fact]
    public void HumanReadableDuration_ReturnsMinutesAndSecondsForMediumDurations()
    {
        var start = new DateTime(2024, 1, 1, 10, 0, 0, DateTimeKind.Utc);
        var end = new DateTime(2024, 1, 1, 10, 5, 30, DateTimeKind.Utc);

        var result = ReportDateUtils.HumanReadableDuration(start, end);
        result.Should().Be("5m 30s");
    }

    [Fact]
    public void HumanReadableDuration_ReturnsHoursAndMinutesForLongDurations()
    {
        var start = new DateTime(2024, 1, 1, 10, 0, 0, DateTimeKind.Utc);
        var end = new DateTime(2024, 1, 1, 12, 30, 0, DateTimeKind.Utc);

        var result = ReportDateUtils.HumanReadableDuration(start, end);
        result.Should().Be("2h 30m");
    }
}

using FluentAssertions;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.Unit;

public class SearchAnalyticsTrackerTests
{
    private readonly SearchAnalyticsTracker _tracker = new();

    [Fact]
    public void GetAnalytics_WhenEmpty_ReturnsZeros()
    {
        var data = _tracker.GetAnalytics();
        data.TotalSearches.Should().Be(0);
        data.AvgResultsPerQuery.Should().Be(0.0);
        data.PopularQueries.Should().BeEmpty();
        data.ZeroResultQueries.Should().BeEmpty();
    }

    [Fact]
    public void Record_SingleQuery_ReflectedInAnalytics()
    {
        _tracker.Record("test query", 5);
        var data = _tracker.GetAnalytics();
        data.TotalSearches.Should().Be(1);
        data.AvgResultsPerQuery.Should().Be(5.0);
        data.PopularQueries.Should().HaveCount(1);
        data.PopularQueries[0]["query"].Should().Be("test query");
    }

    [Fact]
    public void Record_ZeroResults_TrackedSeparately()
    {
        _tracker.Record("no results query", 0);
        var data = _tracker.GetAnalytics();
        data.ZeroResultQueries.Should().HaveCount(1);
        data.ZeroResultQueries[0]["query"].Should().Be("no results query");
    }

    [Fact]
    public void Record_MultipleQueries_OrderedByPopularity()
    {
        _tracker.Record("popular", 10);
        _tracker.Record("popular", 8);
        _tracker.Record("popular", 5);
        _tracker.Record("rare", 3);

        var data = _tracker.GetAnalytics();
        data.TotalSearches.Should().Be(4);
        data.PopularQueries[0]["query"].Should().Be("popular");
        data.PopularQueries[0]["count"].Should().Be(3);
    }

    [Fact]
    public void Record_ThreadSafe_NoConcurrencyErrors()
    {
        var tasks = new List<Task>();
        for (int i = 0; i < 10; i++)
        {
            tasks.Add(Task.Run(() =>
            {
                for (int j = 0; j < 100; j++)
                {
                    _tracker.Record($"query-{j}", j);
                }
            }));
        }

        Task.WaitAll(tasks.ToArray());
        var data = _tracker.GetAnalytics();
        data.TotalSearches.Should().Be(1000);
    }
}

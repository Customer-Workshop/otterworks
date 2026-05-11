using FluentAssertions;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Moq;
using OtterWorks.SearchService.Controllers;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.Unit;

public class SearchControllerTests
{
    private readonly Mock<IMeiliSearchService> _mockSearch = new();
    private readonly Mock<ISearchAnalyticsTracker> _mockAnalytics = new();
    private readonly SearchController _controller;

    public SearchControllerTests()
    {
        _controller = new SearchController(_mockSearch.Object, _mockAnalytics.Object);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public void SearchDocuments_MissingQuery_Returns400()
    {
        var result = _controller.SearchDocuments(null, null, null, null) as BadRequestObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(400);
    }

    [Fact]
    public void SearchDocuments_EmptyQuery_Returns400()
    {
        var result = _controller.SearchDocuments("", null, null, null) as BadRequestObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void SearchDocuments_InvalidPage_Returns400()
    {
        var result = _controller.SearchDocuments("test", null, "not-a-number", null) as BadRequestObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(400);
    }

    [Fact]
    public void SearchDocuments_ValidQuery_Returns200()
    {
        _mockSearch.Setup(s => s.Search("test", null, null, 1, 20))
            .Returns(new SearchResponse
            {
                Results = new List<SearchHit>
                {
                    new SearchHit { Id = "doc-1", Title = "Test", ContentSnippet = "content", Type = "document", OwnerId = "user-1" },
                },
                Total = 1,
                Page = 1,
                PageSize = 20,
                Query = "test",
            });

        var result = _controller.SearchDocuments("test", null, null, null) as OkObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(200);
    }

    [Fact]
    public void SearchDocuments_WithTypeFilter_PassesTypeToService()
    {
        _mockSearch.Setup(s => s.Search("test", "file", null, 1, 20))
            .Returns(new SearchResponse { Results = new(), Total = 0, Page = 1, PageSize = 20, Query = "test" });

        var result = _controller.SearchDocuments("test", "file", null, null) as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void SearchDocuments_WithPagination_CorrectParams()
    {
        _mockSearch.Setup(s => s.Search("test", null, null, 2, 10))
            .Returns(new SearchResponse { Results = new(), Total = 0, Page = 2, PageSize = 10, Query = "test" });

        var result = _controller.SearchDocuments("test", null, "2", "10") as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void Suggest_ShortQuery_ReturnsEmpty()
    {
        var result = _controller.Suggest("a") as OkObjectResult;
        result.Should().NotBeNull();
        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("\"suggestions\":[]");
    }

    [Fact]
    public void Suggest_EmptyQuery_ReturnsEmpty()
    {
        var result = _controller.Suggest("") as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void Suggest_ValidPrefix_ReturnsSuggestions()
    {
        _mockSearch.Setup(s => s.Suggest("te", 10))
            .Returns(new List<string> { "Test Doc 1", "Test Doc 2" });

        var result = _controller.Suggest("te") as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void AdvancedSearch_EmptyBody_Returns200()
    {
        _mockSearch.Setup(s => s.AdvancedSearch(null, null, null, null, null, null, 1, 20))
            .Returns(new SearchResponse { Results = new(), Total = 0, Page = 1, PageSize = 20, Query = "*" });

        var result = _controller.AdvancedSearch(null) as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void AdvancedSearch_WithFilters_Returns200()
    {
        var request = new AdvancedSearchRequest
        {
            Q = "report",
            Type = "document",
            Tags = new List<string> { "finance" },
            DateFrom = "2024-01-01",
            DateTo = "2024-12-31",
            Page = 1,
            Size = 10,
        };

        _mockSearch.Setup(s => s.AdvancedSearch("report", "document", null, It.IsAny<List<string>>(), "2024-01-01", "2024-12-31", 1, 10))
            .Returns(new SearchResponse { Results = new(), Total = 0, Page = 1, PageSize = 10, Query = "report" });

        var result = _controller.AdvancedSearch(request) as OkObjectResult;
        result.Should().NotBeNull();
    }

    [Fact]
    public void Analytics_ReturnsData()
    {
        _mockAnalytics.Setup(a => a.GetAnalytics())
            .Returns(new AnalyticsData
            {
                PopularQueries = new List<Dictionary<string, object>> { new() { ["query"] = "test", ["count"] = 5 } },
                ZeroResultQueries = new List<Dictionary<string, object>>(),
                TotalSearches = 100,
                AvgResultsPerQuery = 3.5,
            });

        var result = _controller.Analytics() as OkObjectResult;
        result.Should().NotBeNull();
    }
}

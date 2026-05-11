using FluentAssertions;
using Microsoft.AspNetCore.Mvc;
using Moq;
using OtterWorks.SearchService.Controllers;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.Unit;

public class HealthControllerTests
{
    private readonly Mock<IMeiliSearchService> _mockSearch = new();
    private readonly HealthController _controller;

    public HealthControllerTests()
    {
        _controller = new HealthController(_mockSearch.Object);
    }

    [Fact]
    public void Health_ReturnsOkWithServiceInfo()
    {
        var result = _controller.Health() as OkObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(200);
        var json = System.Text.Json.JsonSerializer.Serialize(result.Value);
        json.Should().Contain("\"status\":\"healthy\"");
        json.Should().Contain("\"service\":\"search-service\"");
        json.Should().Contain("\"version\":\"0.1.0\"");
    }

    [Fact]
    public void Readiness_WhenMeiliSearchConnected_Returns200()
    {
        _mockSearch.Setup(s => s.Ping()).Returns(true);
        var result = _controller.Readiness() as OkObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(200);
    }

    [Fact]
    public void Readiness_WhenMeiliSearchDisconnected_Returns503()
    {
        _mockSearch.Setup(s => s.Ping()).Returns(false);
        var result = _controller.Readiness() as ObjectResult;
        result.Should().NotBeNull();
        result!.StatusCode.Should().Be(503);
    }
}

using Microsoft.AspNetCore.Mvc;
using Moq;
using OtterWorks.AdminService.Controllers;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Tests.Unit.Controllers;

public class HealthControllerTests
{
    [Fact]
    public void GetHealth_ReturnsHealthyStatus()
    {
        var healthChecker = Mock.Of<IHealthChecker>();
        var controller = new HealthController(healthChecker);

        var result = controller.GetHealth() as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as HealthResponse;
        Assert.NotNull(response);
        Assert.Equal("healthy", response.Status);
        Assert.Equal("admin-service", response.Service);
        Assert.Equal("0.1.0", response.Version);
    }
}

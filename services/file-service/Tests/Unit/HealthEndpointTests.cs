using OtterWorks.FileService.Models;

namespace FileService.Tests.Unit;

public class HealthEndpointTests
{
    [Fact]
    public void HealthResponse_ShouldHaveCorrectDefaults()
    {
        var response = new HealthResponse();

        Assert.Equal("healthy", response.Status);
        Assert.Equal("file-service", response.Service);
        Assert.Equal("0.1.0", response.Version);
    }
}

using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OtterWorks.ApiGateway.Health;

namespace ApiGateway.Tests.Unit;

public class HealthEndpointTests
{
    [Fact]
    public async Task Health_ReturnsHealthy()
    {
        using var host = await new HostBuilder()
            .ConfigureWebHost(webBuilder =>
            {
                webBuilder
                    .UseTestServer()
                    .ConfigureServices(services =>
                    {
                        services.AddRouting();
                    })
                    .Configure(app =>
                    {
                        app.UseRouting();
                        app.UseEndpoints(endpoints =>
                        {
                            endpoints.MapGet("/health", () => Results.Ok(new HealthResponse
                            {
                                Status = "healthy",
                                Service = "api-gateway",
                                Version = "0.1.0",
                            }));
                        });
                    });
            })
            .StartAsync();

        var client = host.GetTestClient();
        var response = await client.GetAsync("/health");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/json; charset=utf-8", response.Content.Headers.ContentType?.ToString());

        var body = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(body);

        Assert.Equal("healthy", json.RootElement.GetProperty("status").GetString());
        Assert.Equal("api-gateway", json.RootElement.GetProperty("service").GetString());
        Assert.Equal("0.1.0", json.RootElement.GetProperty("version").GetString());
    }
}

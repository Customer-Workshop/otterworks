using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace ApiGateway.Tests.Unit;

public class CorsTests
{
    private static async Task<IHost> CreateHostWithCors(string[] allowedOrigins)
    {
        return await new HostBuilder()
            .ConfigureWebHost(webBuilder =>
            {
                webBuilder
                    .UseTestServer()
                    .ConfigureServices(services =>
                    {
                        services.AddRouting();
                        services.AddCors(options =>
                        {
                            options.AddDefaultPolicy(policy =>
                            {
                                policy.WithOrigins(allowedOrigins)
                                      .WithMethods("GET", "POST", "PUT")
                                      .WithHeaders("Content-Type", "Authorization")
                                      .WithExposedHeaders("X-Request-ID")
                                      .AllowCredentials()
                                      .SetPreflightMaxAge(TimeSpan.FromSeconds(600));
                            });
                        });
                    })
                    .Configure(app =>
                    {
                        app.UseRouting();
                        app.UseCors();
                        app.UseEndpoints(endpoints =>
                        {
                            endpoints.MapGet("/api/test", () => Results.Ok("ok"));
                        });
                    });
            })
            .StartAsync();
    }

    [Fact]
    public async Task AllowedOrigin_SetsCorsHeaders()
    {
        using var host = await CreateHostWithCors(new[] { "http://localhost:3000", "http://localhost:4200" });
        var client = host.GetTestClient();

        var request = new HttpRequestMessage(HttpMethod.Get, "/api/test");
        request.Headers.Add("Origin", "http://localhost:3000");

        var response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("http://localhost:3000", response.Headers.GetValues("Access-Control-Allow-Origin").FirstOrDefault());
        Assert.Contains("true", response.Headers.GetValues("Access-Control-Allow-Credentials").FirstOrDefault());
    }

    [Fact]
    public async Task DisallowedOrigin_NoCorsHeaders()
    {
        using var host = await CreateHostWithCors(new[] { "http://localhost:3000" });
        var client = host.GetTestClient();

        var request = new HttpRequestMessage(HttpMethod.Get, "/api/test");
        request.Headers.Add("Origin", "http://evil.com");

        var response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.False(response.Headers.Contains("Access-Control-Allow-Origin"));
    }

    [Fact]
    public async Task PreflightRequest_Returns204()
    {
        using var host = await CreateHostWithCors(new[] { "http://localhost:3000" });
        var client = host.GetTestClient();

        var request = new HttpRequestMessage(HttpMethod.Options, "/api/test");
        request.Headers.Add("Origin", "http://localhost:3000");
        request.Headers.Add("Access-Control-Request-Method", "POST");

        var response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Equal("http://localhost:3000", response.Headers.GetValues("Access-Control-Allow-Origin").FirstOrDefault());
    }

    [Fact]
    public async Task NoOriginHeader_NoCorsHeaders()
    {
        using var host = await CreateHostWithCors(new[] { "http://localhost:3000", "http://localhost:4200" });
        var client = host.GetTestClient();

        var request = new HttpRequestMessage(HttpMethod.Get, "/api/test");

        var response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.False(response.Headers.Contains("Access-Control-Allow-Origin"));
    }
}

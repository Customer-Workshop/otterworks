using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OtterWorks.DocumentService.Config;
using OtterWorks.DocumentService.Data;
using OtterWorks.DocumentService.Services;

namespace DocumentService.Tests;

public class TestWebApplicationFactory : WebApplicationFactory<Program>
{
    public const string TestJwtSecret = "test-jwt-secret-for-unit-tests-pad-to-48-bytes!!";

    private readonly string _dbName = "TestDb_" + Guid.NewGuid().ToString();

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            // Remove existing DbContext registration
            var descriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(DbContextOptions<DocumentDbContext>));
            if (descriptor is not null)
            {
                services.Remove(descriptor);
            }

            // Remove EF Core provider registrations
            var efDescriptors = services
                .Where(d => d.ServiceType.FullName?.Contains("EntityFrameworkCore") == true)
                .ToList();
            foreach (var d in efDescriptors)
            {
                services.Remove(d);
            }

            // Add InMemory database
            services.AddDbContext<DocumentDbContext>(options =>
            {
                options.UseInMemoryDatabase(_dbName);
            });

            // Replace event publisher with no-op
            var publisherDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(IEventPublisher));
            if (publisherDescriptor is not null)
            {
                services.Remove(publisherDescriptor);
            }

            services.AddScoped<IEventPublisher, NoOpEventPublisher>();

            // Configure JWT for tests
            services.Configure<JwtSettings>(opts => opts.Secret = TestJwtSecret);

            // Remove Redis
            var redisDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(StackExchange.Redis.IConnectionMultiplexer));
            if (redisDescriptor is not null)
            {
                services.Remove(redisDescriptor);
            }
        });
    }
}

public class NoOpEventPublisher : IEventPublisher
{
    public Task PublishAsync(string eventType, Dictionary<string, object> payload)
    {
        return Task.CompletedTask;
    }
}

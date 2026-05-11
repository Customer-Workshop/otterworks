using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.SearchService.Config;
using OtterWorks.SearchService.Services;

namespace SearchService.Tests;

public class TestWebApplicationFactory : WebApplicationFactory<Program>
{
    public Mock<IMeilisearchService> MockMeilisearch { get; } = new();
    public Mock<IIndexer> MockIndexer { get; } = new();

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");

        builder.ConfigureServices(services =>
        {
            // Disable authentication for tests
            services.Configure<AuthSettings>(opts =>
            {
                opts.RequireAuth = false;
                opts.ServiceToken = string.Empty;
            });
            // Remove real services
            var meilisearchDescriptors = services.Where(d =>
                d.ServiceType == typeof(IMeilisearchService) ||
                d.ImplementationType == typeof(MeilisearchService)).ToList();
            foreach (var descriptor in meilisearchDescriptors)
            {
                services.Remove(descriptor);
            }

            var indexerDescriptors = services.Where(d =>
                d.ServiceType == typeof(IIndexer) ||
                d.ImplementationType == typeof(Indexer)).ToList();
            foreach (var descriptor in indexerDescriptors)
            {
                services.Remove(descriptor);
            }

            // Remove hosted services (SQS consumer)
            var hostedServiceDescriptors = services.Where(d =>
                d.ServiceType == typeof(Microsoft.Extensions.Hosting.IHostedService) &&
                d.ImplementationType == typeof(OtterWorks.SearchService.Services.SqsConsumer)).ToList();
            foreach (var descriptor in hostedServiceDescriptors)
            {
                services.Remove(descriptor);
            }

            // Register mocks
            services.AddSingleton(MockMeilisearch.Object);
            services.AddSingleton(MockIndexer.Object);

            // Setup default mock behaviors
            MockMeilisearch.Setup(x => x.EnsureIndicesAsync(It.IsAny<CancellationToken>()))
                .Returns(Task.CompletedTask);
            MockMeilisearch.Setup(x => x.PingAsync(It.IsAny<CancellationToken>()))
                .ReturnsAsync(true);
            MockMeilisearch.Setup(x => x.GetAnalytics())
                .Returns(new OtterWorks.SearchService.Models.AnalyticsData());
        });
    }
}

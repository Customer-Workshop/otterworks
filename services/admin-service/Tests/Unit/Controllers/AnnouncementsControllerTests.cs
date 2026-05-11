using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AdminService.Controllers;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Tests.Unit.Controllers;

public class AnnouncementsControllerTests
{
    private readonly AdminDbContext _context;
    private readonly AnnouncementsController _controller;

    public AnnouncementsControllerTests()
    {
        _context = TestDbContext.Create();
        var auditLogger = new AuditLogger(_context, Mock.Of<ILogger<AuditLogger>>());
        _controller = new AnnouncementsController(_context, auditLogger);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public async Task Index_ReturnsAllAnnouncements()
    {
        CreateAnnouncement("Ann 1");
        CreateAnnouncement("Ann 2");
        CreateAnnouncement("Ann 3");

        var result = await _controller.Index(null, null, null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AnnouncementsListResponse;
        Assert.NotNull(response);
        Assert.Equal(3, response.Announcements.Count);
    }

    [Fact]
    public async Task Index_FiltersByStatus()
    {
        CreateAnnouncement("Draft", "draft");
        CreateAnnouncement("Published", "published");

        var result = await _controller.Index("published", null, null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AnnouncementsListResponse;
        Assert.NotNull(response);
        Assert.All(response.Announcements, a => Assert.Equal("published", a.Status));
    }

    [Fact]
    public async Task Create_CreatesNewAnnouncement()
    {
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"announcement\":{\"title\":\"System Update\",\"body\":\"Scheduled maintenance\",\"severity\":\"info\"}}");

        var result = await _controller.Create(body) as ObjectResult;

        Assert.NotNull(result);
        Assert.Equal(201, result.StatusCode);
        Assert.Equal(1, _context.Announcements.Count());
    }

    [Fact]
    public async Task Create_ReturnsErrorsForInvalidParams()
    {
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"announcement\":{\"title\":\"\"}}");

        var result = await _controller.Create(body) as UnprocessableEntityObjectResult;

        Assert.NotNull(result);
        Assert.Equal(422, result.StatusCode);
    }

    [Fact]
    public async Task Update_UpdatesAnnouncement()
    {
        var ann = CreateAnnouncement("Original", "draft");
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"announcement\":{\"status\":\"published\"}}");

        var result = await _controller.Update(ann.Id, body) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AnnouncementResponse;
        Assert.NotNull(response);
        Assert.Equal("published", response.Status);
    }

    [Fact]
    public async Task Destroy_DeletesAnnouncement()
    {
        var ann = CreateAnnouncement("Delete Me");

        var result = await _controller.Destroy(ann.Id) as NoContentResult;

        Assert.NotNull(result);
        Assert.Equal(0, _context.Announcements.Count());
    }

    private Announcement CreateAnnouncement(string title, string status = "draft")
    {
        var ann = new Announcement
        {
            Id = Guid.NewGuid(),
            Title = title,
            Body = "Test body content",
            Severity = "info",
            Status = status,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
        _context.Announcements.Add(ann);
        _context.SaveChanges();
        return ann;
    }
}

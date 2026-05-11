using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace DocumentService.Tests.Unit;

public class TemplatesApiTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly Guid _ownerId = Guid.NewGuid();

    public TemplatesApiTests(TestWebApplicationFactory factory)
    {
        _client = factory.CreateClient();
        _client.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", MakeJwt(_ownerId.ToString()));
    }

    private static string MakeJwt(string userId)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(TestWebApplicationFactory.TestJwtSecret));
        var creds = new SigningCredentials(key, "HS256");
        var claims = new[] { new Claim("user_id", userId) };
        var token = new JwtSecurityToken(claims: claims, signingCredentials: creds);
        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    [Fact]
    public async Task CreateTemplate_Returns201()
    {
        var resp = await _client.PostAsJsonAsync("/api/v1/templates", new
        {
            name = "Meeting Notes",
            description = "Template for meeting notes",
            content = "## Meeting Notes\n\n- Attendees:\n- Agenda:",
            created_by = Guid.NewGuid(),
        });
        Assert.Equal(HttpStatusCode.Created, resp.StatusCode);
        var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Meeting Notes", data.GetProperty("name").GetString());
        Assert.Equal("Template for meeting notes", data.GetProperty("description").GetString());
    }

    [Fact]
    public async Task ListTemplates_ReturnsAll()
    {
        var creator = Guid.NewGuid();
        foreach (var name in new[] { "Alpha", "Beta", "Gamma" })
        {
            await _client.PostAsJsonAsync("/api/v1/templates", new
            {
                name,
                content = $"{name} content",
                created_by = creator,
            });
        }

        var resp = await _client.GetAsync("/api/v1/templates");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(data.GetArrayLength() >= 3);
    }

    [Fact]
    public async Task CreateDocumentFromTemplate_Returns201()
    {
        var templateResp = await _client.PostAsJsonAsync("/api/v1/templates", new
        {
            name = "Blank Doc",
            content = "Start typing here...",
            content_type = "text/plain",
            created_by = Guid.NewGuid(),
        });
        var templateData = await templateResp.Content.ReadFromJsonAsync<JsonElement>();
        var templateId = templateData.GetProperty("id").GetString();

        var resp = await _client.PostAsJsonAsync($"/api/v1/documents/from-template/{templateId}", new
        {
            title = "My New Doc",
            owner_id = _ownerId,
        });
        Assert.Equal(HttpStatusCode.Created, resp.StatusCode);
        var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("My New Doc", data.GetProperty("title").GetString());
        Assert.Equal("Start typing here...", data.GetProperty("content").GetString());
        Assert.Equal("text/plain", data.GetProperty("content_type").GetString());
    }

    [Fact]
    public async Task CreateFromTemplate_NotFound_Returns404()
    {
        var resp = await _client.PostAsJsonAsync($"/api/v1/documents/from-template/{Guid.NewGuid()}", new
        {
            title = "Orphan",
            owner_id = _ownerId,
        });
        Assert.Equal(HttpStatusCode.NotFound, resp.StatusCode);
    }
}

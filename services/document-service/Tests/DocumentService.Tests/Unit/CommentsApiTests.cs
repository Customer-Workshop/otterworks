using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace DocumentService.Tests.Unit;

public class CommentsApiTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly Guid _ownerId = Guid.NewGuid();

    public CommentsApiTests(TestWebApplicationFactory factory)
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

    private async Task<string> CreateDocument()
    {
        var resp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Commented Doc",
            content = "",
            owner_id = _ownerId,
        });
        var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
        return data.GetProperty("id").GetString()!;
    }

    [Fact]
    public async Task AddComment_Returns201()
    {
        var docId = await CreateDocument();
        var authorId = Guid.NewGuid();

        var resp = await _client.PostAsJsonAsync($"/api/v1/documents/{docId}/comments", new
        {
            author_id = authorId,
            content = "Great document!",
        });
        Assert.Equal(HttpStatusCode.Created, resp.StatusCode);
        var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Great document!", data.GetProperty("content").GetString());
        Assert.Equal(authorId.ToString(), data.GetProperty("author_id").GetString());
        Assert.Equal(docId, data.GetProperty("document_id").GetString());
    }

    [Fact]
    public async Task AddComment_DocumentNotFound_Returns404()
    {
        var resp = await _client.PostAsJsonAsync($"/api/v1/documents/{Guid.NewGuid()}/comments", new
        {
            author_id = Guid.NewGuid(),
            content = "Orphan comment",
        });
        Assert.Equal(HttpStatusCode.NotFound, resp.StatusCode);
    }

    [Fact]
    public async Task ListComments_ReturnsAll()
    {
        var docId = await CreateDocument();

        for (var i = 0; i < 3; i++)
        {
            await _client.PostAsJsonAsync($"/api/v1/documents/{docId}/comments", new
            {
                author_id = Guid.NewGuid(),
                content = $"Comment {i}",
            });
        }

        var resp = await _client.GetAsync($"/api/v1/documents/{docId}/comments");
        Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        var data = await resp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(3, data.GetArrayLength());
    }

    [Fact]
    public async Task DeleteComment_Returns204()
    {
        var docId = await CreateDocument();

        var commentResp = await _client.PostAsJsonAsync($"/api/v1/documents/{docId}/comments", new
        {
            author_id = Guid.NewGuid(),
            content = "To delete",
        });
        var commentData = await commentResp.Content.ReadFromJsonAsync<JsonElement>();
        var commentId = commentData.GetProperty("id").GetString();

        var deleteResp = await _client.DeleteAsync($"/api/v1/documents/{docId}/comments/{commentId}");
        Assert.Equal(HttpStatusCode.NoContent, deleteResp.StatusCode);

        var listResp = await _client.GetAsync($"/api/v1/documents/{docId}/comments");
        var listData = await listResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, listData.GetArrayLength());
    }

    [Fact]
    public async Task DeleteComment_NotFound_Returns404()
    {
        var docId = await CreateDocument();
        var resp = await _client.DeleteAsync($"/api/v1/documents/{docId}/comments/{Guid.NewGuid()}");
        Assert.Equal(HttpStatusCode.NotFound, resp.StatusCode);
    }
}

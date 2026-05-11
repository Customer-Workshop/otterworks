using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace DocumentService.Tests.Unit;

public class DocumentsApiTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly Guid _ownerId = Guid.NewGuid();

    public DocumentsApiTests(TestWebApplicationFactory factory)
    {
        _client = factory.CreateClient();
        _client.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", MakeJwt(_ownerId.ToString()));
    }

    private static string MakeJwt(string userId, string algorithm = "HS256", string claimType = "user_id")
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(TestWebApplicationFactory.TestJwtSecret));
        var creds = new SigningCredentials(key, algorithm);
        var claims = new[] { new Claim(claimType, userId) };
        var token = new JwtSecurityToken(claims: claims, signingCredentials: creds, expires: DateTime.UtcNow.AddHours(1));
        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    [Fact]
    public async Task CreateDocument_Returns201()
    {
        var response = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Test Document",
            content = "Hello world",
            owner_id = _ownerId,
        });

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Test Document", data.GetProperty("title").GetString());
        Assert.Equal("Hello world", data.GetProperty("content").GetString());
        Assert.Equal(2, data.GetProperty("word_count").GetInt32());
        Assert.Equal(1, data.GetProperty("version").GetInt32());
        Assert.Equal(_ownerId.ToString(), data.GetProperty("owner_id").GetString());
    }

    [Fact]
    public async Task GetDocument_Returns200()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Doc",
            content = "Body",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        var response = await _client.GetAsync($"/api/v1/documents/{docId}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(docId, data.GetProperty("id").GetString());
    }

    [Fact]
    public async Task GetDocument_NotFound_Returns404()
    {
        var response = await _client.GetAsync($"/api/v1/documents/{Guid.NewGuid()}");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task ListDocuments_ReturnsPaginated()
    {
        var ownerId = Guid.NewGuid();
        var client = CreateAuthenticatedClient(ownerId);
        for (var i = 0; i < 3; i++)
        {
            await client.PostAsJsonAsync("/api/v1/documents", new
            {
                title = $"Doc {i}",
                content = "",
                owner_id = ownerId,
            });
        }

        var response = await client.GetAsync($"/api/v1/documents?owner_id={ownerId}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(3, data.GetProperty("total").GetInt32());
        Assert.Equal(3, data.GetProperty("items").GetArrayLength());
    }

    [Fact]
    public async Task ListDocuments_Pagination()
    {
        var ownerId = Guid.NewGuid();
        var client = CreateAuthenticatedClient(ownerId);
        for (var i = 0; i < 5; i++)
        {
            await client.PostAsJsonAsync("/api/v1/documents", new
            {
                title = $"Doc {i}",
                content = "",
                owner_id = ownerId,
            });
        }

        var response = await client.GetAsync($"/api/v1/documents?owner_id={ownerId}&page=1&size=2");
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(5, data.GetProperty("total").GetInt32());
        Assert.Equal(2, data.GetProperty("items").GetArrayLength());
        Assert.Equal(3, data.GetProperty("pages").GetInt32());
    }

    [Fact]
    public async Task UpdateDocument_Returns200()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Original",
            content = "Old body",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        var response = await _client.PutAsJsonAsync($"/api/v1/documents/{docId}", new
        {
            title = "Updated",
            content = "New body",
        });
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Updated", data.GetProperty("title").GetString());
        Assert.Equal("New body", data.GetProperty("content").GetString());
        Assert.Equal(2, data.GetProperty("version").GetInt32());
    }

    [Fact]
    public async Task PatchDocument_Returns200()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Original",
            content = "Body",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        var response = await _client.PatchAsJsonAsync($"/api/v1/documents/{docId}", new
        {
            title = "Patched Title",
        });
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Patched Title", data.GetProperty("title").GetString());
        Assert.Equal("Body", data.GetProperty("content").GetString());
        Assert.Equal(2, data.GetProperty("version").GetInt32());
    }

    [Fact]
    public async Task DeleteDocument_Returns204()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "To Delete",
            content = "",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        var deleteResp = await _client.DeleteAsync($"/api/v1/documents/{docId}");
        Assert.Equal(HttpStatusCode.NoContent, deleteResp.StatusCode);

        var getResp = await _client.GetAsync($"/api/v1/documents/{docId}");
        Assert.Equal(HttpStatusCode.NotFound, getResp.StatusCode);
    }

    [Fact]
    public async Task DocumentVersions_List()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Versioned",
            content = "v1",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        await _client.PutAsJsonAsync($"/api/v1/documents/{docId}", new
        {
            title = "Versioned",
            content = "v2",
        });

        var versionsResp = await _client.GetAsync($"/api/v1/documents/{docId}/versions");
        Assert.Equal(HttpStatusCode.OK, versionsResp.StatusCode);
        var versions = await versionsResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(2, versions.GetArrayLength());
        Assert.Equal(2, versions[0].GetProperty("version_number").GetInt32());
        Assert.Equal(1, versions[1].GetProperty("version_number").GetInt32());
    }

    [Fact]
    public async Task RestoreVersion_Returns200()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Restore Me",
            content = "Original",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        await _client.PutAsJsonAsync($"/api/v1/documents/{docId}", new
        {
            title = "Changed",
            content = "Changed body",
        });

        var versionsResp = await _client.GetAsync($"/api/v1/documents/{docId}/versions");
        var versions = await versionsResp.Content.ReadFromJsonAsync<JsonElement>();
        var v1Id = versions[versions.GetArrayLength() - 1].GetProperty("id").GetString();

        var restoreResp = await _client.PostAsync($"/api/v1/documents/{docId}/versions/{v1Id}/restore", null);
        Assert.Equal(HttpStatusCode.OK, restoreResp.StatusCode);
        var data = await restoreResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Restore Me", data.GetProperty("title").GetString());
        Assert.Equal("Original", data.GetProperty("content").GetString());
        Assert.Equal(3, data.GetProperty("version").GetInt32());
    }

    [Fact]
    public async Task ExportDocument_Html()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Export",
            content = "Content here",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        var response = await _client.GetAsync($"/api/v1/documents/{docId}/export?format=html");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var text = await response.Content.ReadAsStringAsync();
        Assert.Contains("<h1>Export</h1>", text);
    }

    [Fact]
    public async Task ExportDocument_Markdown()
    {
        var createResp = await _client.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "Export MD",
            content = "MD content",
            owner_id = _ownerId,
        });
        var createData = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var docId = createData.GetProperty("id").GetString();

        var response = await _client.GetAsync($"/api/v1/documents/{docId}/export?format=markdown");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var text = await response.Content.ReadAsStringAsync();
        Assert.Contains("# Export MD", text);
    }

    [Fact]
    public async Task CreateDocument_ViaJwt()
    {
        var userId = Guid.NewGuid();
        var token = MakeJwt(userId.ToString());
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/documents")
        {
            Content = JsonContent.Create(new { title = "JWT Doc", content = "Created via JWT" }),
        };
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token);

        var response = await _client.SendAsync(request);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("JWT Doc", data.GetProperty("title").GetString());
        Assert.Equal(userId.ToString(), data.GetProperty("owner_id").GetString());
    }

    [Fact]
    public async Task CreateDocument_ViaJwt_HS384()
    {
        var userId = Guid.NewGuid();
        var token = MakeJwt(userId.ToString(), "HS384", "sub");
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/documents")
        {
            Content = JsonContent.Create(new { title = "HS384 Doc" }),
        };
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token);

        var response = await _client.SendAsync(request);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var data = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(userId.ToString(), data.GetProperty("owner_id").GetString());
    }

    [Fact]
    public async Task CreateDocument_NoAuth_Returns401()
    {
        var noAuthClient = new TestWebApplicationFactory().CreateClient();

        var response = await noAuthClient.PostAsJsonAsync("/api/v1/documents", new
        {
            title = "No Auth Doc",
        });
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    private HttpClient CreateAuthenticatedClient(Guid userId)
    {
        var client = new TestWebApplicationFactory().CreateClient();
        client.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", MakeJwt(userId.ToString()));
        return client;
    }
}

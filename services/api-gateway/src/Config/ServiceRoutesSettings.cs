namespace OtterWorks.ApiGateway.Config;

public class ServiceRoutesSettings
{
    public string Auth { get; set; } = "http://auth-service:8081";
    public string File { get; set; } = "http://file-service:8082";
    public string Document { get; set; } = "http://document-service:8083";
    public string Collab { get; set; } = "http://collab-service:8084";
    public string Notification { get; set; } = "http://notification-service:8086";
    public string Search { get; set; } = "http://search-service:8087";
    public string Analytics { get; set; } = "http://analytics-service:8088";
    public string Admin { get; set; } = "http://admin-service:8089";
    public string Audit { get; set; } = "http://audit-service:8090";
    public string Report { get; set; } = "http://report-service:8091";

    public Dictionary<string, string> GetRouteMap()
    {
        return new Dictionary<string, string>
        {
            ["/api/v1/auth"] = Auth,
            ["/api/v1/files"] = File,
            ["/api/v1/folders"] = File,
            ["/api/v1/documents"] = Document,
            ["/api/v1/templates"] = Document,
            ["/api/v1/collab"] = Collab,
            ["/socket.io"] = Collab,
            ["/api/v1/notifications"] = Notification,
            ["/api/v1/preferences"] = Notification,
            ["/api/v1/search"] = Search,
            ["/api/v1/analytics"] = Analytics,
            ["/api/v1/admin"] = Admin,
            ["/api/v1/audit"] = Audit,
            ["/api/v1/reports"] = Report,
            ["/api/v1/settings"] = Auth,
        };
    }
}

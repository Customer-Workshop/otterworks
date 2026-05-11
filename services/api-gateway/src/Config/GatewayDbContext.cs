using Microsoft.EntityFrameworkCore;

namespace OtterWorks.ApiGateway.Config;

public class GatewayDbContext : DbContext
{
    public GatewayDbContext(DbContextOptions<GatewayDbContext> options)
        : base(options)
    {
    }
}

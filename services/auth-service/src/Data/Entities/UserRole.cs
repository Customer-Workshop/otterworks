using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AuthService.Data.Entities;

[Table("user_roles")]
public class UserRole
{
    [Column("user_id")]
    public Guid UserId { get; set; }

    [Column("role")]
    public string Role { get; set; } = string.Empty;
}

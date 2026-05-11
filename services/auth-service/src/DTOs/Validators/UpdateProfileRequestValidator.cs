using FluentValidation;

namespace OtterWorks.AuthService.DTOs.Validators;

public sealed class UpdateProfileRequestValidator : AbstractValidator<UpdateProfileRequest>
{
    public UpdateProfileRequestValidator()
    {
        RuleFor(x => x.DisplayName).MinimumLength(1).MaximumLength(100).When(x => x.DisplayName != null);
        RuleFor(x => x.AvatarUrl).MaximumLength(500).When(x => x.AvatarUrl != null);
    }
}

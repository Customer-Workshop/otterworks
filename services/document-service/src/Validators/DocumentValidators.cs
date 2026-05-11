using FluentValidation;
using OtterWorks.DocumentService.DTOs;

namespace OtterWorks.DocumentService.Validators;

public class DocumentCreateRequestValidator : AbstractValidator<DocumentCreateRequest>
{
    public DocumentCreateRequestValidator()
    {
        RuleFor(x => x.Title).NotEmpty().MaximumLength(500);
    }
}

public class DocumentUpdateRequestValidator : AbstractValidator<DocumentUpdateRequest>
{
    public DocumentUpdateRequestValidator()
    {
        RuleFor(x => x.Title).NotEmpty().MaximumLength(500);
    }
}

public class CommentCreateRequestValidator : AbstractValidator<CommentCreateRequest>
{
    public CommentCreateRequestValidator()
    {
        RuleFor(x => x.Content).NotEmpty();
    }
}

public class TemplateCreateRequestValidator : AbstractValidator<TemplateCreateRequest>
{
    public TemplateCreateRequestValidator()
    {
        RuleFor(x => x.Name).NotEmpty().MaximumLength(500);
    }
}

public class DocumentFromTemplateRequestValidator : AbstractValidator<DocumentFromTemplateRequest>
{
    public DocumentFromTemplateRequestValidator()
    {
        RuleFor(x => x.Title).NotEmpty().MaximumLength(500);
    }
}

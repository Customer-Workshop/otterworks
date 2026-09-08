using System.Globalization;
using System.Text.Json;

namespace AuditService.Tests;

/// <summary>
/// Minimal JSON Schema (draft-07 subset) checker for contract tests: type, const, enum,
/// required, properties, additionalProperties, items, minItems, local $ref and the
/// uuid/date-time formats.
/// </summary>
public sealed class JsonSchemaAssert
{
    private readonly JsonElement _root;

    private JsonSchemaAssert(JsonElement root) => _root = root;

    public static JsonSchemaAssert Load(string schemaFile)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(SharedSchemaPath(schemaFile)));
        return new JsonSchemaAssert(doc.RootElement.Clone());
    }

    public JsonElement Definition(string name)
    {
        if (!_root.GetProperty("definitions").TryGetProperty(name, out var def))
        {
            throw new Xunit.Sdk.XunitException($"Definition '{name}' not found in schema");
        }
        return def;
    }

    public void ConformsTo(JsonElement schema, JsonElement instance)
    {
        var violations = Validate(schema, instance, "$");
        if (violations.Count > 0)
        {
            throw new Xunit.Sdk.XunitException(
                $"Payload violates contract:\n  {string.Join("\n  ", violations)}\nPayload: {instance}");
        }
    }

    public List<string> Validate(JsonElement schema, JsonElement instance, string path)
    {
        var violations = new List<string>();

        if (schema.TryGetProperty("$ref", out var reference))
            violations.AddRange(Validate(Resolve(reference.GetString()!), instance, path));

        if (schema.TryGetProperty("const", out var constant) && !JsonEquals(constant, instance))
            violations.Add($"{path}: expected const {constant}, got {instance}");

        if (schema.TryGetProperty("enum", out var allowedValues) &&
            !allowedValues.EnumerateArray().Any(v => JsonEquals(v, instance)))
            violations.Add($"{path}: {instance} not in enum {allowedValues}");

        if (schema.TryGetProperty("type", out var typeNode))
        {
            var allowed = typeNode.ValueKind == JsonValueKind.Array
                ? typeNode.EnumerateArray().Select(t => t.GetString()!).ToList()
                : new List<string> { typeNode.GetString()! };
            if (!allowed.Any(t => MatchesType(t, instance)))
                violations.Add($"{path}: expected type [{string.Join(", ", allowed)}], got {instance.ValueKind}");
        }

        if (instance.ValueKind == JsonValueKind.String && schema.TryGetProperty("format", out var format))
        {
            var text = instance.GetString()!;
            switch (format.GetString())
            {
                case "uuid" when !Guid.TryParse(text, out _):
                    violations.Add($"{path}: '{text}' is not a uuid");
                    break;
                case "date-time" when !DateTimeOffset.TryParseExact(
                    text,
                    new[] { "yyyy-MM-dd'T'HH:mm:ssK", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFFK" },
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.None,
                    out _):
                    violations.Add($"{path}: '{text}' is not an RFC 3339 date-time");
                    break;
            }
        }

        if (instance.ValueKind == JsonValueKind.Object)
        {
            var hasProperties = schema.TryGetProperty("properties", out var properties);
            if (schema.TryGetProperty("required", out var required))
            {
                foreach (var name in required.EnumerateArray().Select(r => r.GetString()!))
                {
                    if (!instance.TryGetProperty(name, out _))
                        violations.Add($"{path}: missing required property '{name}'");
                }
            }

            var hasAdditional = schema.TryGetProperty("additionalProperties", out var additional);
            foreach (var property in instance.EnumerateObject())
            {
                if (hasProperties && properties.TryGetProperty(property.Name, out var propertySchema))
                    violations.AddRange(Validate(propertySchema, property.Value, $"{path}.{property.Name}"));
                else if (hasAdditional && additional.ValueKind == JsonValueKind.Object)
                    violations.AddRange(Validate(additional, property.Value, $"{path}.{property.Name}"));
                else if (hasAdditional && additional.ValueKind == JsonValueKind.False)
                    violations.Add($"{path}: property '{property.Name}' is not declared in the contract");
            }
        }

        if (instance.ValueKind == JsonValueKind.Array)
        {
            var length = instance.GetArrayLength();
            if (schema.TryGetProperty("minItems", out var minItems) && length < minItems.GetInt32())
                violations.Add($"{path}: expected at least {minItems.GetInt32()} items, got {length}");

            if (schema.TryGetProperty("items", out var itemSchema))
            {
                var i = 0;
                foreach (var item in instance.EnumerateArray())
                    violations.AddRange(Validate(itemSchema, item, $"{path}[{i++}]"));
            }
        }

        return violations;
    }

    private JsonElement Resolve(string pointer)
    {
        if (!pointer.StartsWith("#/", StringComparison.Ordinal))
            throw new Xunit.Sdk.XunitException($"Only local $ref pointers are supported, got '{pointer}'");

        var node = _root;
        foreach (var segment in pointer[2..].Split('/'))
        {
            var key = segment.Replace("~1", "/").Replace("~0", "~");
            if (!node.TryGetProperty(key, out node))
                throw new Xunit.Sdk.XunitException($"$ref '{pointer}' does not resolve");
        }
        return node;
    }

    private static bool MatchesType(string type, JsonElement instance) => type switch
    {
        "object" => instance.ValueKind == JsonValueKind.Object,
        "array" => instance.ValueKind == JsonValueKind.Array,
        "null" => instance.ValueKind == JsonValueKind.Null,
        "string" => instance.ValueKind == JsonValueKind.String,
        "boolean" => instance.ValueKind is JsonValueKind.True or JsonValueKind.False,
        "integer" => instance.ValueKind == JsonValueKind.Number && instance.TryGetInt64(out _),
        "number" => instance.ValueKind == JsonValueKind.Number,
        _ => false,
    };

    private static bool JsonEquals(JsonElement a, JsonElement b) => a.GetRawText() == b.GetRawText();

    private static string SharedSchemaPath(string schemaFile)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "shared", "events", "schemas", schemaFile);
            if (File.Exists(candidate)) return candidate;
            dir = dir.Parent;
        }
        throw new Xunit.Sdk.XunitException(
            $"Could not locate shared/events/schemas/{schemaFile} above {AppContext.BaseDirectory}");
    }
}

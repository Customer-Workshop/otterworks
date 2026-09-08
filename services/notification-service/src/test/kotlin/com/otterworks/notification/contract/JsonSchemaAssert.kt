package com.otterworks.notification.contract

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.fail

/**
 * Minimal JSON Schema (draft-07 subset) checker for contract tests: type, const, enum,
 * required, properties, additionalProperties, items, minItems and the uuid/date-time formats.
 */
object JsonSchemaAssert {

    fun loadDefinition(schemaFile: String, definition: String): JsonObject {
        val schema = Json.parseToJsonElement(Files.readString(sharedSchemaPath(schemaFile))).jsonObject
        return schema["definitions"]?.jsonObject?.get(definition)?.jsonObject
            ?: fail("Definition '$definition' not found in $schemaFile")
    }

    fun assertConformsTo(schema: JsonObject, instance: JsonElement) {
        val violations = validate(schema, instance, "$")
        if (violations.isNotEmpty()) {
            fail("Payload violates contract:\n  ${violations.joinToString("\n  ")}\nPayload: $instance")
        }
    }

    fun validate(schema: JsonObject, instance: JsonElement, path: String): List<String> {
        val violations = mutableListOf<String>()

        schema["const"]?.let { if (it != instance) violations += "$path: expected const $it, got $instance" }
        schema["enum"]?.jsonArray?.let { if (instance !in it) violations += "$path: $instance not in enum $it" }

        schema["type"]?.let { typeNode ->
            val allowed = when (typeNode) {
                is JsonArray -> typeNode.map { it.jsonPrimitive.content }
                else -> listOf(typeNode.jsonPrimitive.content)
            }
            if (allowed.none { matchesType(it, instance) }) {
                violations += "$path: expected type $allowed, got ${describe(instance)}"
            }
        }

        if (instance is JsonPrimitive && instance.isString) {
            when (schema["format"]?.jsonPrimitive?.contentOrNull) {
                "uuid" -> runCatching { UUID.fromString(instance.content) }
                    .onFailure { violations += "$path: '${instance.content}' is not a uuid" }
                "date-time" -> runCatching { OffsetDateTime.parse(instance.content) }
                    .onFailure { violations += "$path: '${instance.content}' is not an RFC 3339 date-time" }
            }
        }

        if (instance is JsonObject) {
            val properties = schema["properties"]?.jsonObject ?: JsonObject(emptyMap())
            schema["required"]?.jsonArray?.forEach { req ->
                val name = req.jsonPrimitive.content
                if (name !in instance) violations += "$path: missing required property '$name'"
            }
            instance.forEach { (name, value) ->
                val propertySchema = properties[name]?.jsonObject
                when {
                    propertySchema != null -> violations += validate(propertySchema, value, "$path.$name")
                    schema["additionalProperties"] is JsonObject ->
                        violations += validate(schema["additionalProperties"]!!.jsonObject, value, "$path.$name")
                    schema["additionalProperties"]?.jsonPrimitive?.booleanOrNull == false ->
                        violations += "$path: property '$name' is not declared in the contract"
                }
            }
        }

        if (instance is JsonArray) {
            schema["minItems"]?.jsonPrimitive?.intOrNull?.let { min ->
                if (instance.size < min) violations += "$path: expected at least $min items, got ${instance.size}"
            }
            schema["items"]?.jsonObject?.let { itemSchema ->
                instance.forEachIndexed { i, item -> violations += validate(itemSchema, item, "$path[$i]") }
            }
        }

        return violations
    }

    private fun matchesType(type: String, instance: JsonElement): Boolean = when (type) {
        "object" -> instance is JsonObject
        "array" -> instance is JsonArray
        "null" -> instance is JsonNull
        "string" -> instance is JsonPrimitive && instance.isString
        "boolean" -> instance is JsonPrimitive && !instance.isString && instance.booleanOrNull != null
        "integer" -> instance is JsonPrimitive && !instance.isString && instance.content.toLongOrNull() != null
        "number" -> instance is JsonPrimitive && !instance.isString && instance.content.toDoubleOrNull() != null
        else -> false
    }

    private fun describe(instance: JsonElement): String = when (instance) {
        is JsonObject -> "object"
        is JsonArray -> "array"
        is JsonNull -> "null"
        is JsonPrimitive -> if (instance.isString) "string" else "literal ${instance.content}"
    }

    private fun sharedSchemaPath(schemaFile: String): Path {
        var dir: Path? = Paths.get("").toAbsolutePath()
        while (dir != null) {
            val candidate = dir.resolve("shared/events/schemas/$schemaFile")
            if (Files.exists(candidate)) return candidate
            dir = dir.parent
        }
        fail("Could not locate shared/events/schemas/$schemaFile above ${Paths.get("").toAbsolutePath()}")
    }
}

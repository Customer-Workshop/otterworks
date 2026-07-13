package com.otterworks.android.data.model

import com.google.gson.annotations.SerializedName

// --- Auth (camelCase JSON) ---

data class RegisterRequest(
    val displayName: String,
    val email: String,
    val password: String,
)

data class LoginRequest(
    val email: String,
    val password: String,
)

data class AuthUser(
    val id: String,
    val email: String,
    val displayName: String,
)

data class AuthResponse(
    val accessToken: String,
    val refreshToken: String?,
    val tokenType: String?,
    val expiresIn: Long?,
    val user: AuthUser?,
)

// --- Documents (snake_case JSON) ---

data class Document(
    val id: String,
    val title: String,
    val content: String?,
    @SerializedName("content_type") val contentType: String?,
    @SerializedName("owner_id") val ownerId: String?,
    @SerializedName("folder_id") val folderId: String?,
    @SerializedName("is_deleted") val isDeleted: Boolean?,
    @SerializedName("word_count") val wordCount: Int?,
    val version: Int?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("updated_at") val updatedAt: String?,
)

data class CreateDocumentRequest(
    val title: String,
)

data class DocumentListResponse(
    val items: List<Document> = emptyList(),
    val total: Int = 0,
    val page: Int = 1,
    val size: Int = 20,
    val pages: Int = 1,
)

// --- Files (snake_case JSON) ---

data class FileItem(
    val id: String,
    val name: String?,
    @SerializedName("mime_type") val mimeType: String?,
    val size: Long?,
    @SerializedName("owner_id") val ownerId: String?,
    @SerializedName("created_at") val createdAt: String?,
)

data class FileListResponse(
    val files: List<FileItem> = emptyList(),
    val total: Int = 0,
    val page: Int = 1,
    @SerializedName("page_size") val pageSize: Int = 50,
)

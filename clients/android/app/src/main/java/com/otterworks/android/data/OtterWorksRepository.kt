package com.otterworks.android.data

import com.otterworks.android.data.model.AuthResponse
import com.otterworks.android.data.model.CreateDocumentRequest
import com.otterworks.android.data.model.Document
import com.otterworks.android.data.model.FileItem
import com.otterworks.android.data.model.LoginRequest
import com.otterworks.android.data.model.RegisterRequest
import com.otterworks.android.data.remote.ApiService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Single entry point for data operations. Wraps the [ApiService] and persists the
 * auth token via [TokenStore].
 */
class OtterWorksRepository(
    private val api: ApiService,
    private val tokenStore: TokenStore,
) {

    val displayName: String?
        get() = tokenStore.displayName

    fun isLoggedIn(): Boolean = tokenStore.isLoggedIn()

    suspend fun register(displayName: String, email: String, password: String) =
        withContext(Dispatchers.IO) {
            val response = api.register(RegisterRequest(displayName, email, password))
            persist(response, fallbackName = displayName)
            response
        }

    suspend fun login(email: String, password: String) =
        withContext(Dispatchers.IO) {
            val response = api.login(LoginRequest(email, password))
            persist(response, fallbackName = null)
            response
        }

    suspend fun listDocuments(): List<Document> =
        withContext(Dispatchers.IO) { api.listDocuments().items }

    suspend fun createDocument(title: String): Document =
        withContext(Dispatchers.IO) { api.createDocument(CreateDocumentRequest(title)) }

    suspend fun listFiles(): List<FileItem> =
        withContext(Dispatchers.IO) { api.listFiles().files }

    fun logout() = tokenStore.clear()

    private fun persist(response: AuthResponse, fallbackName: String?) {
        tokenStore.save(
            token = response.accessToken,
            displayName = response.user?.displayName ?: fallbackName,
        )
    }
}

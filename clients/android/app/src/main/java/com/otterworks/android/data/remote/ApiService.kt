package com.otterworks.android.data.remote

import com.otterworks.android.data.model.AuthResponse
import com.otterworks.android.data.model.CreateDocumentRequest
import com.otterworks.android.data.model.Document
import com.otterworks.android.data.model.DocumentListResponse
import com.otterworks.android.data.model.FileListResponse
import com.otterworks.android.data.model.LoginRequest
import com.otterworks.android.data.model.RegisterRequest
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface ApiService {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): AuthResponse

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): AuthResponse

    @GET("documents")
    suspend fun listDocuments(): DocumentListResponse

    @POST("documents")
    suspend fun createDocument(@Body body: CreateDocumentRequest): Document

    @GET("files")
    suspend fun listFiles(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 50,
    ): FileListResponse
}

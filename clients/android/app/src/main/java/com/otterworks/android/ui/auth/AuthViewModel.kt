package com.otterworks.android.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.otterworks.android.data.OtterWorksRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class AuthUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val success: Boolean = false,
)

class AuthViewModel(
    private val repository: OtterWorksRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AuthUiState())
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    fun register(displayName: String, email: String, password: String) {
        val validation = validate(displayName, email, password)
        if (validation != null) {
            _state.value = AuthUiState(error = validation)
            return
        }
        run { repository.register(displayName.trim(), email.trim(), password) }
    }

    fun login(email: String, password: String) {
        if (email.isBlank() || password.isBlank()) {
            _state.value = AuthUiState(error = "Email and password are required")
            return
        }
        run { repository.login(email.trim(), password) }
    }

    fun consumeError() {
        _state.value = _state.value.copy(error = null)
    }

    private fun run(block: suspend () -> Unit) {
        _state.value = AuthUiState(loading = true)
        viewModelScope.launch {
            try {
                block()
                _state.value = AuthUiState(success = true)
            } catch (e: Exception) {
                _state.value = AuthUiState(error = friendlyError(e))
            }
        }
    }

    private fun validate(displayName: String, email: String, password: String): String? = when {
        displayName.isBlank() -> "Display name is required"
        email.isBlank() -> "Email is required"
        password.length < 8 -> "Password must be at least 8 characters"
        else -> null
    }

    private fun friendlyError(e: Exception): String {
        val http = e as? retrofit2.HttpException
        return when (http?.code()) {
            400 -> "Invalid details. Please check your input."
            401 -> "Incorrect email or password."
            409 -> "An account with that email already exists."
            else -> e.message ?: "Something went wrong. Please try again."
        }
    }
}

package com.otterworks.android.ui.documents

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.otterworks.android.data.OtterWorksRepository
import com.otterworks.android.data.model.Document
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class DocumentsUiState(
    val loading: Boolean = false,
    val documents: List<Document> = emptyList(),
    val error: String? = null,
    val creating: Boolean = false,
)

class DocumentsViewModel(
    private val repository: OtterWorksRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(DocumentsUiState())
    val state: StateFlow<DocumentsUiState> = _state.asStateFlow()

    val displayName: String?
        get() = repository.displayName

    fun refresh() {
        _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            try {
                val docs = repository.listDocuments()
                _state.value = _state.value.copy(loading = false, documents = docs)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = e.message ?: "Failed to load documents",
                )
            }
        }
    }

    fun createDocument(title: String, onDone: () -> Unit) {
        if (title.isBlank()) return
        _state.value = _state.value.copy(creating = true, error = null)
        viewModelScope.launch {
            try {
                repository.createDocument(title.trim())
                _state.value = _state.value.copy(creating = false)
                onDone()
                refresh()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    creating = false,
                    error = e.message ?: "Failed to create document",
                )
            }
        }
    }

    fun logout() = repository.logout()

    fun consumeError() {
        _state.value = _state.value.copy(error = null)
    }
}

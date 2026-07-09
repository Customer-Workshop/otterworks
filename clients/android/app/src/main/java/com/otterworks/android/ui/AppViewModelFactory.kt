package com.otterworks.android.ui

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.otterworks.android.OtterWorksApplication
import com.otterworks.android.ui.auth.AuthViewModel
import com.otterworks.android.ui.documents.DocumentsViewModel

/** Provides ViewModels wired with the app-level repository. */
object AppViewModelFactory {
    val instance: ViewModelProvider.Factory = viewModelFactory {
        initializer { AuthViewModel(app().repository) }
        initializer { DocumentsViewModel(app().repository) }
    }

    private fun CreationExtras.app(): OtterWorksApplication =
        this[APPLICATION_KEY] as OtterWorksApplication
}

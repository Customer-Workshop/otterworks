package com.otterworks.android.ui.auth

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun RegisterScreen(
    viewModel: AuthViewModel,
    onRegistered: () -> Unit,
    onNavigateToLogin: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var displayName by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(state.success) {
        if (state.success) onRegistered()
    }

    AuthScaffold(title = "Create your account") {
        AuthTextField(
            value = displayName,
            onValueChange = { displayName = it },
            label = "Display name",
        )
        AuthTextField(
            value = email,
            onValueChange = { email = it },
            label = "Email",
            keyboardType = KeyboardType.Email,
        )
        AuthTextField(
            value = password,
            onValueChange = { password = it },
            label = "Password (min 8 chars)",
            isPassword = true,
            keyboardType = KeyboardType.Password,
        )

        InlineError(state.error)

        Button(
            onClick = { viewModel.register(displayName, email, password) },
            enabled = !state.loading,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 12.dp),
        ) {
            Text(if (state.loading) "Creating..." else "Register")
        }

        TextButton(onClick = onNavigateToLogin) {
            Text("Already have an account? Sign in")
        }

        if (state.loading) LoadingIndicator()
    }
}

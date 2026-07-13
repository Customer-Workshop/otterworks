package com.otterworks.android.ui.documents

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DocumentsScreen(
    viewModel: DocumentsViewModel,
    onLoggedOut: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showCreateDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.refresh() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Documents")
                        viewModel.displayName?.let {
                            Text(
                                text = "Signed in as $it",
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                    }
                },
                actions = {
                    IconButton(onClick = {
                        viewModel.logout()
                        onLoggedOut()
                    }) {
                        Icon(Icons.Filled.Logout, contentDescription = "Log out")
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showCreateDialog = true }) {
                Icon(Icons.Filled.Add, contentDescription = "Create document")
            }
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            when {
                state.loading && state.documents.isEmpty() -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                }

                state.documents.isEmpty() -> EmptyState()

                else -> DocumentList(state.documents)
            }

            state.error?.let {
                Text(
                    text = it,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(16.dp),
                )
            }
        }
    }

    if (showCreateDialog) {
        CreateDocumentDialog(
            creating = state.creating,
            onDismiss = { showCreateDialog = false },
            onConfirm = { title ->
                viewModel.createDocument(title) { showCreateDialog = false }
            },
        )
    }
}

@Composable
private fun EmptyState() {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            Icons.Filled.Description,
            contentDescription = null,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        Text("No documents yet", style = MaterialTheme.typography.titleMedium)
        Text(
            "Tap + to create your first document.",
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun DocumentList(documents: List<com.otterworks.android.data.model.Document>) {
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(documents, key = { it.id }) { doc ->
            ListItem(
                headlineContent = {
                    Text(
                        text = doc.title.ifBlank { "Untitled" },
                        fontWeight = FontWeight.Medium,
                    )
                },
                supportingContent = doc.updatedAt?.let { { Text("Updated $it") } },
                leadingContent = {
                    Icon(Icons.Filled.Description, contentDescription = null)
                },
            )
            HorizontalDivider()
        }
    }
}

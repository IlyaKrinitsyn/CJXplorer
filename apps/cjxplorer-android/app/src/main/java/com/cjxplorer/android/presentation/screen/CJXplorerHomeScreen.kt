package com.cjxplorer.android.presentation.screen

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.cjxplorer.android.presentation.CJXplorerUiState

@Composable
fun CJXplorerHomeScreen(
    uiState: CJXplorerUiState,
    onConnect: (String) -> Unit,
    onDisconnect: () -> Unit,
    modifier: Modifier = Modifier
) {
    var taskIdInput by remember { mutableStateOf("") }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "CJXplorer",
            style = MaterialTheme.typography.headlineMedium
        )

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val statusColor = if (uiState.isConnected) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.error
                    }
                    Surface(
                        shape = MaterialTheme.shapes.small,
                        color = statusColor,
                        modifier = Modifier.size(12.dp)
                    ) {}
                    Text(
                        text = if (uiState.isConnected) "Подключено" else "Отключено",
                        style = MaterialTheme.typography.titleMedium
                    )
                }

                if (uiState.taskId.isNotEmpty()) {
                    Text(
                        text = "Задача: ${uiState.taskId}",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                    Text(
                        text = "Шаг: ${uiState.currentStep}",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }

        OutlinedTextField(
            value = taskIdInput,
            onValueChange = { taskIdInput = it },
            label = { Text("Task ID") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = { onConnect(taskIdInput) },
                enabled = taskIdInput.isNotBlank() && !uiState.isConnected
            ) {
                Text("Подключиться")
            }

            OutlinedButton(
                onClick = onDisconnect,
                enabled = uiState.isConnected
            ) {
                Text("Остановить")
            }
        }

        Text(
            text = "Лог",
            style = MaterialTheme.typography.titleMedium
        )

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            items(uiState.logs) { log ->
                Text(
                    text = log,
                    style = MaterialTheme.typography.labelMedium
                )
            }
        }
    }
}

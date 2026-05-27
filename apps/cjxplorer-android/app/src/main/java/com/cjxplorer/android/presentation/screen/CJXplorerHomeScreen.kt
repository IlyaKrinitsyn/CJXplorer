package com.cjxplorer.android.presentation.screen

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.cjxplorer.android.presentation.CJXplorerUiState

@Composable
fun CJXplorerHomeScreen(
    uiState: CJXplorerUiState,
    onSaveUrl: (String) -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
    onStopNavigation: () -> Unit,
    onRequestProjection: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
    modifier: Modifier = Modifier
) {
    var serverUrlInput by remember(uiState.serverUrl) { mutableStateOf(uiState.serverUrl) }
    val logListState = rememberLazyListState()

    LaunchedEffect(uiState.logs.size) {
        if (uiState.logs.isNotEmpty()) {
            logListState.animateScrollToItem(uiState.logs.lastIndex)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = "CJXplorer",
            style = MaterialTheme.typography.headlineMedium
        )

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Сервер", style = MaterialTheme.typography.titleSmall)

                OutlinedTextField(
                    value = serverUrlInput,
                    onValueChange = { serverUrlInput = it },
                    label = { Text("Адрес сервера (ws://host:port)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    enabled = !uiState.isDeviceConnected
                )

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    when {
                        uiState.isDeviceConnected -> {
                            OutlinedButton(onClick = onDisconnect) {
                                Text("Отключиться")
                            }
                        }
                        uiState.isConnecting -> {
                            CircularProgressIndicator(modifier = Modifier.size(20.dp))
                            Text(
                                text = "Подключение...",
                                style = MaterialTheme.typography.bodySmall
                            )
                            OutlinedButton(onClick = onDisconnect) {
                                Text("Отмена")
                            }
                        }
                        else -> {
                            Button(
                                onClick = {
                                    onSaveUrl(serverUrlInput)
                                    onConnect()
                                },
                                enabled = serverUrlInput.isNotBlank()
                            ) {
                                Text("Подключиться")
                            }
                        }
                    }
                }

                val error = uiState.connectionError
                if (error != null) {
                    Text(
                        text = error,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Запись экрана", style = MaterialTheme.typography.titleSmall)

                if (uiState.hasProjectionPermission) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Surface(
                            shape = MaterialTheme.shapes.small,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(12.dp)
                        ) {}
                        Text("Разрешение получено", style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    Text(
                        text = "Для навигации нужен доступ к записи экрана",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Button(onClick = onRequestProjection) {
                        Text("Разрешить запись экрана")
                    }
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Accessibility", style = MaterialTheme.typography.titleSmall)

                if (uiState.isAccessibilityEnabled) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Surface(
                            shape = MaterialTheme.shapes.small,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(12.dp)
                        ) {}
                        Text("Сервис включён", style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    Text(
                        text = "Для навигации по приложениям нужен Accessibility Service",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Button(onClick = onOpenAccessibilitySettings) {
                        Text("Открыть настройки Accessibility")
                    }
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val statusColor = when {
                        uiState.isDeviceConnected -> MaterialTheme.colorScheme.primary
                        uiState.isConnecting -> MaterialTheme.colorScheme.tertiary
                        uiState.connectionError != null -> MaterialTheme.colorScheme.error
                        else -> MaterialTheme.colorScheme.outline
                    }
                    val statusText = when {
                        uiState.isDeviceConnected -> "Подключено"
                        uiState.isConnecting -> "Подключение..."
                        uiState.connectionError != null -> "Ошибка подключения"
                        else -> "Отключено"
                    }
                    Surface(
                        shape = MaterialTheme.shapes.small,
                        color = statusColor,
                        modifier = Modifier.size(12.dp)
                    ) {}
                    Text(
                        text = statusText,
                        style = MaterialTheme.typography.titleMedium
                    )
                }

                val task = uiState.currentTask
                if (task != null) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Задача: ${task.taskId}",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    if (task.appName.isNotEmpty()) {
                        Text(
                            text = "Приложение: ${task.appName}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    Text(
                        text = "Сценарий: ${task.journeyDescription}",
                        style = MaterialTheme.typography.bodySmall
                    )

                    if (uiState.isNavigating) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(16.dp))
                            Text("Навигация...", style = MaterialTheme.typography.bodySmall)
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        OutlinedButton(onClick = onStopNavigation) {
                            Text("Остановить навигацию")
                        }
                    }
                } else if (uiState.isDeviceConnected) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Ожидание задачи...",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        Text(
            text = "Лог",
            style = MaterialTheme.typography.titleMedium
        )

        LazyColumn(
            state = logListState,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            items(uiState.logs) { log ->
                Text(
                    text = log,
                    style = MaterialTheme.typography.labelSmall
                )
            }
        }
    }
}

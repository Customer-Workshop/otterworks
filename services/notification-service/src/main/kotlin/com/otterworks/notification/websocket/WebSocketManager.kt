package com.otterworks.notification.websocket

import com.otterworks.notification.model.Notification
import io.ktor.websocket.DefaultWebSocketSession
import io.ktor.websocket.Frame
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import mu.KotlinLogging
import java.util.concurrent.ConcurrentHashMap

private val logger = KotlinLogging.logger {}

class WebSocketManager {

    private val connections = ConcurrentHashMap<String, MutableSet<DefaultWebSocketSession>>()

    private val json = Json {
        prettyPrint = false
        ignoreUnknownKeys = true
    }

    fun addConnection(userId: String, session: DefaultWebSocketSession) {
        connections.getOrPut(userId) { ConcurrentHashMap.newKeySet() }.add(session)
        logger.info { "WebSocket connected for user $userId (total: ${connections[userId]?.size ?: 0})" }
    }

    fun removeConnection(userId: String, session: DefaultWebSocketSession) {
        connections.computeIfPresent(userId) { _, sessions ->
            sessions.remove(session)
            if (sessions.isEmpty()) null else sessions
        }
        logger.info { "WebSocket disconnected for user $userId" }
    }

    suspend fun pushNotification(userId: String, notification: Notification) {
        val sessions = connections[userId] ?: return

        val payload = json.encodeToString(notification)
        val deadSessions = mutableListOf<DefaultWebSocketSession>()

        for (session in sessions) {
            try {
                session.send(Frame.Text(payload))
                logger.debug { "Pushed notification ${notification.id} to user $userId via WebSocket" }
            } catch (e: Exception) {
                logger.warn { "Failed to push to WebSocket for user $userId: ${e.message}" }
                deadSessions.add(session)
            }
        }

        deadSessions.forEach { removeConnection(userId, it) }
    }

    fun getConnectedUserCount(): Int = connections.size

    fun isUserConnected(userId: String): Boolean = connections.containsKey(userId)
}

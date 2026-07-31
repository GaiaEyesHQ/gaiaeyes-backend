package com.gaiaeyes.app.core.quicklog

import android.content.Intent
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class QuickLogCoordinator(
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) {
    private val _pending = MutableStateFlow<QuickLogRequest?>(null)
    val pending: StateFlow<QuickLogRequest?> = _pending.asStateFlow()

    private var lastAcceptedKind: QuickLogKind? = null
    private var lastAcceptedAtEpochMillis: Long = Long.MIN_VALUE

    fun handleIntent(intent: Intent): Boolean {
        val kind = parseQuickLogAction(
            action = intent.action,
            data = intent.dataString,
        ) ?: return false
        offer(kind)
        return true
    }

    internal fun offer(kind: QuickLogKind): Boolean {
        val now = nowEpochMillis()
        val duplicatePending = _pending.value?.kind == kind
        val duplicateDelivery =
            lastAcceptedKind == kind &&
                now - lastAcceptedAtEpochMillis in 0 until DUPLICATE_WINDOW_MILLIS
        if (duplicatePending || duplicateDelivery) return false

        lastAcceptedKind = kind
        lastAcceptedAtEpochMillis = now
        _pending.value = QuickLogRequest(
            id = UUID.randomUUID().toString(),
            kind = kind,
            requestedAtEpochMillis = now,
        )
        return true
    }

    fun consume(requestId: String) {
        if (_pending.value?.id == requestId) {
            _pending.value = null
        }
    }

    private companion object {
        const val DUPLICATE_WINDOW_MILLIS = 15_000L
    }
}

data class QuickLogRequest(
    val id: String,
    val kind: QuickLogKind,
    val requestedAtEpochMillis: Long,
)

enum class QuickLogKind(
    val symptomCode: String,
    val defaultSeverity: Int,
) {
    MIGRAINE(
        symptomCode = "MIGRAINE",
        defaultSeverity = 5,
    ),
}

internal fun parseQuickLogAction(
    action: String?,
    data: String?,
): QuickLogKind? {
    if (action == ACTION_LOG_MIGRAINE) return QuickLogKind.MIGRAINE
    val normalizedData = data?.trim()?.trimEnd('/')?.lowercase()
    return if (normalizedData == MIGRAINE_DEEP_LINK) QuickLogKind.MIGRAINE else null
}

const val ACTION_LOG_MIGRAINE = "com.gaiaeyes.app.action.LOG_MIGRAINE"
private const val MIGRAINE_DEEP_LINK = "gaiaeyes://log/migraine"

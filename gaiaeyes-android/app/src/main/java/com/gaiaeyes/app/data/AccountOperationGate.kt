package com.gaiaeyes.app.data

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.withTimeout

enum class AccountDeletionRecord { PAUSED, SUBMITTED, CONFIRMED, COMPLETE }

interface AccountDeletionRecords {
    fun read(accountId: String): AccountDeletionRecord?
    fun write(accountId: String, record: AccountDeletionRecord?)
}

class AccountWorkPausedException : CancellationException("Account sync is paused for deletion")

/** Tracks the whole caller job, including its queue/cache writes after an HTTP response. */
class AccountOperationGate(private val records: AccountDeletionRecords) {
    private val lock = Any()
    private val active = mutableMapOf<String, MutableSet<Job>>()
    private val blocked = mutableSetOf<String>()

    fun isBlocked(accountId: String): Boolean = synchronized(lock) {
        accountId in blocked || records.read(accountId) != null
    }

    fun requireActive(accountId: String) {
        if (isBlocked(accountId)) throw AccountWorkPausedException()
    }

    suspend fun track(accountId: String) {
        val context = currentCoroutineContext()
        context.ensureActive()
        val job = checkNotNull(context[Job])
        synchronized(lock) {
            requireActive(accountId)
            if (active.getOrPut(accountId) { mutableSetOf() }.add(job)) {
                job.invokeOnCompletion {
                    synchronized(lock) {
                        active[accountId]?.remove(job)
                        if (active[accountId]?.isEmpty() == true) active.remove(accountId)
                    }
                }
            }
        }
    }

    suspend fun pauseAndCancel(accountId: String) {
        val caller = currentCoroutineContext()[Job]
        val jobs = synchronized(lock) {
            blocked.add(accountId)
            if (records.read(accountId) == null) records.write(accountId, AccountDeletionRecord.PAUSED)
            active[accountId].orEmpty().toList().also { check(caller !in it) }
        }
        jobs.forEach { it.cancel(AccountWorkPausedException()) }
        // Never send DELETE if old client operations have not actually finished.
        withTimeout(15_000) { jobs.joinAll() }
    }

    fun resumeBeforeSubmission(accountId: String) = synchronized(lock) {
        check(records.read(accountId) in listOf(null, AccountDeletionRecord.PAUSED))
        records.write(accountId, null)
        blocked.remove(accountId)
    }
}

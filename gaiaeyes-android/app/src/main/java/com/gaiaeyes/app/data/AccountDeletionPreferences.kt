package com.gaiaeyes.app.data

import android.content.Context
import java.security.MessageDigest

/** Minimal account-hash marker prevents old uploads after an interrupted deletion. No health data. */
class AccountDeletionPreferences(context: Context) : AccountDeletionRecords {
    private val preferences = context.getSharedPreferences("gaia_account_deletion", Context.MODE_PRIVATE)

    override fun read(accountId: String): AccountDeletionRecord? =
        preferences.getString(key(accountId), null)?.let { value ->
            // An unknown saved state must fail closed, not resume uploads.
            AccountDeletionRecord.entries.firstOrNull { it.name == value } ?: AccountDeletionRecord.SUBMITTED
        }

    override fun write(accountId: String, record: AccountDeletionRecord?) {
        val editor = preferences.edit()
        if (record == null) editor.remove(key(accountId)) else editor.putString(key(accountId), record.name)
        check(editor.commit()) { "Could not save the account deletion state" }
    }

    private fun key(accountId: String): String = MessageDigest.getInstance("SHA-256")
        .digest(accountId.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
}

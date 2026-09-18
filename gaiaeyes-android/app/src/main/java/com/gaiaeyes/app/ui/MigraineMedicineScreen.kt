package com.gaiaeyes.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gaiaeyes.app.core.network.MigraineMedicine
import com.gaiaeyes.app.ui.theme.*

@Composable
internal fun MigraineMedicineScreen(state: MigraineMedicineState, controller: MigraineMedicineController, modifier: Modifier = Modifier) {
    val actions = controller.actions(state.sessionId)
    val editing = state.phase == MigraineMedicinePhase.EDITING && !state.confirmDiscard
    val fieldsEnabled = editing && state.editor == null
    val scroll = rememberScrollState()
    LaunchedEffect(state.phase, state.message) {
        if (state.editor == null && (state.phase != MigraineMedicinePhase.EDITING || state.message != null)) scroll.scrollTo(0)
    }
    BackHandler(onBack = actions::close)
    Scaffold(modifier.fillMaxSize(), containerColor = GaiaNavy,
        topBar = {
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 20.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Edit medicines", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                TextButton(onClick = actions::close) { Text("Close") }
            }
        },
        bottomBar = {
            Column(Modifier.fillMaxWidth().background(GaiaPanel).navigationBarsPadding().imePadding().padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (state.editor != null) Text("Apply or cancel the medicine edit before saving.", color = GaiaAmber)
                when (state.phase) {
                    MigraineMedicinePhase.EDITING -> Button(onClick = actions::save, enabled = fieldsEnabled, modifier = Modifier.fillMaxWidth()) { Text("Save medicines") }
                    MigraineMedicinePhase.UNAVAILABLE, MigraineMedicinePhase.UNCERTAIN -> Button(onClick = actions::retry, enabled = !state.confirmDiscard, modifier = Modifier.fillMaxWidth()) { Text("Retry same changes") }
                    MigraineMedicinePhase.REVIEW -> Button(onClick = actions::useReviewed, enabled = !state.confirmDiscard, modifier = Modifier.fillMaxWidth()) { Text("Use reviewed version") }
                    MigraineMedicinePhase.REVIEWED, MigraineMedicinePhase.SAVED -> Button(onClick = actions::close, modifier = Modifier.fillMaxWidth()) { Text("Done") }
                    else -> Unit
                }
                if (state.phase in setOf(MigraineMedicinePhase.UNCERTAIN, MigraineMedicinePhase.CONFLICT)) {
                    OutlinedButton(onClick = actions::review, enabled = !state.confirmDiscard, modifier = Modifier.fillMaxWidth()) { Text("Review saved medicines") }
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().verticalScroll(scroll).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text(medicineStatus(state.phase), color = if (state.phase == MigraineMedicinePhase.SAVED) GaiaGreen else Color.White)
            if (state.phase in setOf(MigraineMedicinePhase.SAVING, MigraineMedicinePhase.REVIEWING)) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (state.editor == null) state.message?.let { Text(it, color = GaiaAmber) }
            state.reviewed?.let { MedicineListReadback("Latest saved medicines", it.episode.medicines) }
            state.saved?.let { MedicineListReadback("Saved medicines", it.episode.medicines) }
            if (state.saved == null) {
                Card(colors = CardDefaults.cardColors(containerColor = GaiaPanel), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(if (editing) "Medicines" else if (state.phase == MigraineMedicinePhase.REVIEWED) "Earlier draft (set aside)" else "Your kept medicines", color = GaiaRose, fontWeight = FontWeight.Bold)
                        if (state.medicines.isEmpty()) Text(if (state.hasChanges) "All medicine entries are removed in this draft. Save medicines to clear them." else "No medicine entries recorded.", color = Color.White)
                        state.medicines.forEachIndexed { index, row -> key(row.id) {
                            Text("${index + 1}. ${row.value.name}", color = Color.White, fontWeight = FontWeight.Bold)
                            MedicineReadback(row.value)
                            if (fieldsEnabled) Row {
                                TextButton(onClick = { actions.edit(row.id) }) { Text("Edit") }
                                TextButton(onClick = { actions.remove(row.id) }) { Text("Remove") }
                                TextButton(onClick = { actions.move(index, index - 1) }, enabled = index > 0) { Text("Move up") }
                            }
                            HorizontalDivider()
                        } }
                        if (fieldsEnabled) OutlinedButton(onClick = { actions.edit(null) }, modifier = Modifier.fillMaxWidth()) { Text("Add medicine") }
                        state.editor?.let { editor ->
                            Text("Changing relief records the time you apply this entry. Unchanged relief keeps its recorded time.", color = Color(0xFFADB7C5))
                            MedicineEditor(editor, state.message, editing, actions::change, actions::apply, actions::cancel)
                        }
                    }
                }
            }
            if (state.phase !in setOf(MigraineMedicinePhase.SAVED, MigraineMedicinePhase.REVIEWED)) {
                Text("These changes stay in memory while the editor is open. Closing the app can lose an unconfirmed edit.", color = Color(0xFFADB7C5), fontSize = 12.sp)
            }
        }
    }
    if (state.confirmDiscard) AlertDialog(onDismissRequest = actions::keep,
        title = { Text("Discard medicine changes?") },
        text = { Text("Your local draft will be discarded. A save already sent may still complete; closing does not undo it.") },
        confirmButton = { TextButton(onClick = actions::discard) { Text("Discard changes and close") } },
        dismissButton = { TextButton(onClick = actions::keep) { Text("Keep editing") } },
    )
}

@Composable
private fun MedicineListReadback(title: String, medicines: List<MigraineMedicine>) {
    Card(colors = CardDefaults.cardColors(containerColor = GaiaPanel), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, color = GaiaRose, fontWeight = FontWeight.Bold)
            if (medicines.isEmpty()) Text("No medicine entries recorded.", color = Color.White)
            medicines.forEachIndexed { index, value ->
                Text("${index + 1}. ${value.name}", color = Color.White, fontWeight = FontWeight.Bold)
                MedicineReadback(value)
            }
        }
    }
}
private fun medicineStatus(phase: MigraineMedicinePhase): String = when (phase) {
    MigraineMedicinePhase.CLOSED -> ""
    MigraineMedicinePhase.EDITING -> "Update medicines for this saved episode. Other episode details stay as recorded."
    MigraineMedicinePhase.SAVING -> "Saving medicine changes…"
    MigraineMedicinePhase.UNAVAILABLE -> "Saving medicines is unavailable. Your changes are kept; retry sends the same changes."
    MigraineMedicinePhase.UNCERTAIN -> "We couldn't confirm the save. Your changes are kept. Retry sends the same changes, or review the saved medicines."
    MigraineMedicinePhase.CONFLICT -> "This episode changed. Your medicine changes are kept; review the saved version before deciding."
    MigraineMedicinePhase.REVIEWING -> "Loading saved medicines for comparison…"
    MigraineMedicinePhase.REVIEW -> "Compare the saved medicines with your kept changes. This check does not confirm your earlier save."
    MigraineMedicinePhase.REVIEWED -> "Your earlier changes were set aside, not confirmed as saved. Close this editor and refresh the saved summary before editing again."
    MigraineMedicinePhase.DELETED -> "This episode is no longer available. Your local changes are kept until you close the editor."
    MigraineMedicinePhase.SAVED -> "Medicines saved."
}

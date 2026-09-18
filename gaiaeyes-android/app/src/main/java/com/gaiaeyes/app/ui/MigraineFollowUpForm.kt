package com.gaiaeyes.app.ui

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.ui.theme.*
import java.time.LocalDate
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
internal fun MigraineFollowUpForm(
    state: MigraineFollowUpState,
    ui: MigraineFollowUpFormUi,
    controller: MigraineFollowUpFormController,
    modifier: Modifier = Modifier,
) {
    val actions = controller.actions(ui.sessionId)
    BackHandler(onBack = actions::requestClose)
    val editing = state.phase == MigraineFollowUpPhase.EDITING && !ui.confirmDiscard
    val fieldsEnabled = editing && ui.medicine == null
    Scaffold(
        modifier = modifier.fillMaxSize(), containerColor = GaiaNavy,
        topBar = {
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 20.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Migraine follow-up", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f))
                TextButton(onClick = actions::requestClose) { Text("Close") }
            }
        },
        bottomBar = {
            Column(Modifier.fillMaxWidth().background(GaiaPanel).navigationBarsPadding().imePadding().padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (ui.medicine != null) Text("Apply or cancel the medicine edit before saving.", color = GaiaAmber)
                migraineFormActions(state).forEachIndexed { index, action ->
                    if (index == 0) Button(onClick = { actions.action(action) },
                        enabled = ui.medicine == null && !ui.confirmDiscard, modifier = Modifier.fillMaxWidth()) { Text(action.label) }
                    else OutlinedButton(onClick = { actions.action(action) }, enabled = !ui.confirmDiscard,
                        modifier = Modifier.fillMaxWidth()) { Text(action.label) }
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text(ui.selection?.question?.takeIf { it.isNotBlank() } ?: "How is this migraine now?",
                color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
            FormSection("Response") {
                Text(migraineFormStatus(state), color = if (state.phase == MigraineFollowUpPhase.SAVED) GaiaGreen else Color.White)
                if (state.phase in setOf(MigraineFollowUpPhase.LOADING, MigraineFollowUpPhase.SAVING, MigraineFollowUpPhase.REVIEWING)) {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                }
                when (state.problem) {
                    MigraineFollowUpProblem.INVALID_INPUT -> Text("Check medicine entries and any empty sign or context fields before saving.", color = GaiaAmber)
                    MigraineFollowUpProblem.REJECTED -> Text("Some answers were rejected. Review the kept response.", color = GaiaAmber)
                    MigraineFollowUpProblem.SIGN_IN -> Text("Your session needs attention. Your response has not been confirmed.", color = GaiaAmber)
                    MigraineFollowUpProblem.INVALID_RESPONSE -> Text("The saved result couldn't be verified.", color = GaiaAmber)
                    MigraineFollowUpProblem.CANCELLED -> Text("The request was interrupted.", color = GaiaAmber)
                    MigraineFollowUpProblem.NETWORK -> if (state.phase != MigraineFollowUpPhase.UNAVAILABLE) Text("The request couldn't be completed or confirmed.", color = GaiaAmber)
                    null -> Unit
                }
            }
            state.baseline?.let { detail ->
                Text("Episode started ${displayMigraineTime(detail.episode.start.utc)} • Severity ${detail.episode.severity?.let { "$it/10" } ?: "not recorded"}", color = Color(0xFFADB7C5))
            }
            state.reviewed?.let { ReviewedMigraineDetails(it, "Latest saved version") }
            state.saved?.let { ReviewedMigraineDetails(it.migraineDetail, "Saved response") }
            state.draft?.let { draft ->
                if (!editing) Text("Your kept response", color = GaiaRose, fontWeight = FontWeight.Bold)
                FormSection("How is it now?") {
                    Choices(draft.answers.state, listOf("ongoing" to "Still active", "improving" to "Improving", "worse" to "Worse", "resolved" to "Resolved"), fieldsEnabled) {
                        actions.answers(draft.answers.copy(state = it ?: "ongoing", detailChoice = null, timeBucket = null))
                    }
                    if (draft.answers.state == "resolved") {
                        Text("When did it settle? (optional)", color = Color.White)
                        Choices(draft.answers.timeBucket, listOf("within_1_hour" to "Within an hour", "later_same_day" to "Later that day", "overnight" to "Overnight", "not_sure" to "Not sure"), fieldsEnabled, allowClear = true) {
                            actions.answers(draft.answers.copy(timeBucket = it))
                        }
                    } else {
                        Text("What fits? (optional)", color = Color.White)
                        Choices(draft.answers.detailChoice, listOf("head_pressure" to "Head pressure", "sinus_pressure" to "Sinus pressure", "other" to "Other"), fieldsEnabled, allowClear = true) {
                            actions.answers(draft.answers.copy(detailChoice = it))
                        }
                    }
                    FormText(draft.answers.detailText ?: "", "Other detail (optional)", fieldsEnabled) {
                        actions.answers(draft.answers.copy(detailText = it.takeIf(String::isNotBlank)))
                    }
                    FormText(draft.answers.noteText ?: "", "Note for this response (optional)", fieldsEnabled, singleLine = false) {
                        actions.answers(draft.answers.copy(noteText = it.takeIf(String::isNotBlank)))
                    }
                }
                FormSection("Medicines") {
                    if (draft.medicines.isEmpty()) Text("No medicine entries recorded.", color = Color(0xFFADB7C5))
                    draft.medicines.forEachIndexed { index, row -> key(row.id) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("${index + 1}. ${row.value.name}", color = Color.White, fontWeight = FontWeight.Bold)
                            MedicineReadback(row.value)
                            if (fieldsEnabled) {
                                Row {
                                    TextButton(onClick = { actions.editMedicine(row.id) }) { Text("Edit") }
                                    TextButton(onClick = { actions.removeMedicine(row.id) }) { Text("Remove") }
                                    TextButton(onClick = { actions.moveMedicine(index, index - 1) }, enabled = index > 0) { Text("Move up") }
                                }
                            }
                        }
                        HorizontalDivider()
                    } }
                    if (fieldsEnabled) OutlinedButton(onClick = { actions.editMedicine(null) }, modifier = Modifier.fillMaxWidth()) { Text("Add medicine") }
                    ui.medicine?.let { editor ->
                        MedicineEditor(editor, ui.message, editing, actions::medicine, actions::applyMedicine, actions::cancelMedicine)
                    }
                }
                FormSection("Early signs") {
                    val signs = draft.answers.earlySigns ?: state.baseline!!.episode.earlySigns
                    if (signs.isEmpty()) Text("No early signs recorded.", color = Color(0xFFADB7C5))
                    signs.forEachIndexed { index, sign ->
                        FormText(sign.label, "Sign ${index + 1}", fieldsEnabled) { actions.earlySign(index, it) }
                        sign.notes?.let { Text(it, color = Color(0xFFADB7C5)) }
                        if (fieldsEnabled) TextButton(onClick = { actions.earlySign(index, null) }) { Text("Remove sign ${index + 1}") }
                    }
                    if (fieldsEnabled) TextButton(onClick = { actions.earlySign(null, "") }) { Text("Add an early sign") }
                }
                FormSection("Context and exposures") {
                    val contexts = draft.answers.contexts ?: state.baseline!!.episode.contexts
                    if (contexts.isEmpty()) Text("No context recorded.", color = Color(0xFFADB7C5))
                    contexts.forEachIndexed { index, context ->
                        FormText(context.label, "Context ${index + 1}", fieldsEnabled) { actions.context(index, it) }
                        Text("${context.kind.replaceFirstChar(Char::titlecase)} • ${context.source.replace('_', ' ')}", color = Color(0xFFADB7C5))
                        context.notes?.let { Text(it, color = Color(0xFFADB7C5)) }
                        if (fieldsEnabled) TextButton(onClick = { actions.context(index, null) }) { Text("Remove context ${index + 1}") }
                    }
                    if (fieldsEnabled) TextButton(onClick = { actions.context(null, "") }) { Text("Add context") }
                }
                FormSection("Episode notes") {
                    val notes = when (val change = draft.answers.notes) {
                        MigraineTextChange.Retain -> state.baseline?.episode?.notes ?: ""
                        MigraineTextChange.Clear -> ""
                        is MigraineTextChange.Set -> change.value
                    }
                    FormText(notes, "Episode notes (optional)", fieldsEnabled, singleLine = false) {
                        actions.answers(draft.answers.copy(notes = if (it.isBlank()) MigraineTextChange.Clear else MigraineTextChange.Set(it)))
                    }
                }
                Text("This draft stays in memory while this form is open. Closing the app can lose an unconfirmed response.", color = Color(0xFFADB7C5), fontSize = 12.sp)
            }
        }
    }
    if (ui.confirmDiscard) AlertDialog(
        onDismissRequest = actions::keepEditing,
        title = { Text("Close this response?") },
        text = { Text("Your local draft will be discarded. A save already sent may still complete; closing does not undo it.") },
        confirmButton = { TextButton(onClick = actions::discardAndClose) { Text("Discard draft and close") } },
        dismissButton = { TextButton(onClick = actions::keepEditing) { Text("Keep response") } },
    )
}

@Composable
internal fun MedicineEditor(editor: MigraineMedicineForm, message: String?, enabled: Boolean,
    change: (MigraineMedicineForm) -> Unit, onApply: () -> Unit, onCancel: () -> Unit) {
    val context = LocalContext.current
    Text(if (editor.rowId == null) "New medicine entry" else "Edit medicine entry", color = GaiaRose, fontWeight = FontWeight.Bold)
    FormText(editor.name, "Medicine name", enabled) { change(editor.copy(name = it)) }
    FormText(editor.amount, "Dose (optional)", enabled, keyboard = KeyboardType.Decimal) { change(editor.copy(amount = it)) }
    FormText(editor.unit, "Unit, such as mg (optional)", enabled) { change(editor.copy(unit = it)) }
    Text("Taken at • ${editor.zoneId}", color = Color.White)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(enabled = enabled, modifier = Modifier.weight(1f), onClick = {
            val date = editor.takenAt.toLocalDate()
            DatePickerDialog(context, { _, year, month, day ->
                val updated = LocalDate.of(year, month + 1, day).atTime(editor.takenAt.toLocalTime())
                change(editor.copy(takenAt = updated, offset = if (updated == editor.takenAt) editor.offset else null))
            }, date.year, date.monthValue - 1, date.dayOfMonth).show()
        }) { Text(editor.takenAt.toLocalDate().format(DateTimeFormatter.ofPattern("MMM d, yyyy"))) }
        OutlinedButton(enabled = enabled, modifier = Modifier.weight(1f), onClick = {
            TimePickerDialog(context, { _, hour, minute ->
                val old = editor.takenAt
                val updated = if (old.hour == hour && old.minute == minute) old else old.toLocalDate().atTime(LocalTime.of(hour, minute))
                change(editor.copy(takenAt = updated, offset = if (updated == old) editor.offset else null))
            }, editor.takenAt.hour, editor.takenAt.minute, false).show()
        }) { Text(editor.takenAt.format(DateTimeFormatter.ofPattern("h:mm a"))) }
    }
    val offsets = ZoneId.of(editor.zoneId).rules.getValidOffsets(editor.takenAt)
    if (offsets.size > 1) {
        Text("This time occurs twice. Choose the UTC offset.", color = GaiaAmber)
        Choices(editor.offset?.id, offsets.map { it.id to "UTC${it.id}" }, enabled) { value ->
            change(editor.copy(offset = offsets.firstOrNull { it.id == value }))
        }
    }
    Text("Reported relief (optional)", color = Color.White)
    Choices(editor.relief, listOf("none" to "None", "a_little" to "A little", "some" to "Some", "a_lot" to "A lot", "complete" to "Complete", "unknown" to "Unknown"), enabled, allowClear = true) {
        change(editor.copy(relief = it))
    }
    FormText(editor.notes, "Medicine note (optional)", enabled, singleLine = false) { change(editor.copy(notes = it)) }
    message?.let { Text(it, color = GaiaAmber) }
    Button(onClick = onApply, enabled = enabled, modifier = Modifier.fillMaxWidth()) { Text("Apply entry") }
    TextButton(onClick = onCancel, enabled = enabled) { Text("Cancel entry edit") }
}

@Composable
internal fun MedicineReadback(medicine: MigraineMedicine) {
    Text("${medicine.doseAmount?.toPlainString()?.let { "$it ${medicine.doseUnit}" } ?: "Dose not recorded"} • ${displayMigraineTime(medicine.takenAt.utc)}", color = Color(0xFFADB7C5))
    Text("Relief: ${medicine.reportedRelief?.replace('_', ' ') ?: "not recorded"}", color = Color(0xFFADB7C5))
    medicine.notes?.let { Text(it, color = Color(0xFFADB7C5)) }
}
@Composable
private fun ReviewedMigraineDetails(detail: MigraineDetail, title: String) {
    FormSection(title) {
        Text("State: ${detail.episode.state} • Severity: ${detail.episode.severity?.let { "$it/10" } ?: "not recorded"}", color = Color.White)
        if (detail.episode.medicines.isEmpty()) Text("No medicine entries recorded.", color = Color(0xFFADB7C5))
        detail.episode.medicines.forEachIndexed { index, value ->
            Text("${index + 1}. ${value.name}", color = Color.White); MedicineReadback(value)
        }
        Text("Early signs: ${detail.episode.earlySigns.joinToString { it.label }.ifEmpty { "not recorded" }}", color = Color(0xFFADB7C5))
        Text("Context: ${detail.episode.contexts.joinToString { it.label }.ifEmpty { "not recorded" }}", color = Color(0xFFADB7C5))
        Text("Notes: ${detail.episode.notes ?: "not recorded"}", color = Color(0xFFADB7C5))
    }
}
@Composable
private fun FormSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = GaiaPanel), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, color = GaiaRose, fontWeight = FontWeight.Bold)
            content()
        }
    }
}
@Composable
private fun FormText(value: String, label: String, enabled: Boolean, singleLine: Boolean = true,
    keyboard: KeyboardType = KeyboardType.Text, change: (String) -> Unit) {
    OutlinedTextField(value, change, label = { Text(label) }, enabled = enabled, singleLine = singleLine,
        minLines = if (singleLine) 1 else 2, keyboardOptions = KeyboardOptions(keyboardType = keyboard), modifier = Modifier.fillMaxWidth())
}
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Choices(value: String?, choices: List<Pair<String, String>>, enabled: Boolean, allowClear: Boolean = false, change: (String?) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        choices.forEach { (key, label) -> FilterChip(selected = value == key, onClick = { change(key) }, label = { Text(label) }, enabled = enabled) }
        if (allowClear) FilterChip(selected = value == null, onClick = { change(null) }, label = { Text("Not recorded") }, enabled = enabled)
    }
}
private fun displayMigraineTime(value: String): String = runCatching {
    OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("MMM d, h:mm a z"))
}.getOrDefault("Time unavailable")

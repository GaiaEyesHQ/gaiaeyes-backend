package com.gaiaeyes.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.gaiaeyes.app.ui.theme.GaiaBlue
import com.gaiaeyes.app.ui.theme.GaiaNavy
import com.gaiaeyes.app.ui.theme.GaiaPanel

@Composable
fun JournalDialogHost(
    uiState: HomeUiState,
    onDismiss: () -> Unit,
    onSubmitSymptom: (String, Int, String?) -> Unit,
    onSubmitExposure: (String, Int, String?) -> Unit,
    onSubmitDailyCheckIn: (String, String, String, String, String, String, String?) -> Unit,
) {
    when (uiState.journalDialog) {
        JournalDialog.SYMPTOM -> SymptomLogDialog(
            uiState = uiState,
            onDismiss = onDismiss,
            onSubmit = onSubmitSymptom,
        )
        JournalDialog.EXPOSURE -> ExposureLogDialog(
            uiState = uiState,
            onDismiss = onDismiss,
            onSubmit = onSubmitExposure,
        )
        JournalDialog.DAILY_CHECK_IN -> DailyCheckInDialog(
            uiState = uiState,
            onDismiss = onDismiss,
            onSubmit = onSubmitDailyCheckIn,
        )
        null -> Unit
    }
}

@Composable
private fun SymptomLogDialog(
    uiState: HomeUiState,
    onDismiss: () -> Unit,
    onSubmit: (String, Int, String?) -> Unit,
) {
    var selectedCode by rememberSaveable { mutableStateOf("") }
    var severity by rememberSaveable { mutableIntStateOf(5) }
    var note by rememberSaveable { mutableStateOf("") }

    JournalDialogFrame(
        title = "Log a symptom",
        subtitle = "What are you noticing right now?",
        isLoading = uiState.isLoadingJournal,
        isSubmitting = uiState.isSubmittingJournal,
        canSubmit = selectedCode.isNotBlank(),
        onDismiss = onDismiss,
        onSubmit = { onSubmit(selectedCode, severity, note) },
    ) {
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 340.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(
                items = uiState.symptomCatalog,
                key = { it.symptomCode },
            ) { item ->
                SelectableJournalRow(
                    label = item.label,
                    selected = item.symptomCode == selectedCode,
                    onClick = { selectedCode = item.symptomCode },
                )
            }
        }
        JournalChoiceGroup(
            title = "Intensity",
            choices = listOf(
                "Mild" to 3,
                "Noticeable" to 5,
                "Strong" to 7,
                "Severe" to 9,
            ),
            selected = severity,
            onSelected = { severity = it },
        )
        JournalNoteField(note = note, onNoteChanged = { note = it })
    }
}

@Composable
private fun ExposureLogDialog(
    uiState: HomeUiState,
    onDismiss: () -> Unit,
    onSubmit: (String, Int, String?) -> Unit,
) {
    var selectedKey by rememberSaveable { mutableStateOf("") }
    var intensity by rememberSaveable { mutableIntStateOf(1) }
    var note by rememberSaveable { mutableStateOf("") }

    JournalDialogFrame(
        title = "Log an exposure",
        subtitle = "Add something that may be useful context for how you feel.",
        isLoading = uiState.isLoadingJournal,
        isSubmitting = uiState.isSubmittingJournal,
        canSubmit = selectedKey.isNotBlank(),
        onDismiss = onDismiss,
        onSubmit = { onSubmit(selectedKey, intensity, note) },
    ) {
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 340.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(
                items = uiState.exposureCatalog,
                key = { it.exposureKey },
            ) { item ->
                SelectableJournalRow(
                    label = item.label,
                    selected = item.exposureKey == selectedKey,
                    onClick = { selectedKey = item.exposureKey },
                )
            }
        }
        JournalChoiceGroup(
            title = "Intensity",
            choices = listOf(
                "Light" to 1,
                "Noticeable" to 2,
                "Strong" to 3,
            ),
            selected = intensity,
            onSelected = { intensity = it },
        )
        JournalNoteField(note = note, onNoteChanged = { note = it })
    }
}

@Composable
private fun DailyCheckInDialog(
    uiState: HomeUiState,
    onDismiss: () -> Unit,
    onSubmit: (String, String, String, String, String, String, String?) -> Unit,
) {
    var compared by rememberSaveable { mutableStateOf("same") }
    var energy by rememberSaveable { mutableStateOf("manageable") }
    var usableEnergy by rememberSaveable { mutableStateOf("enough") }
    var systemLoad by rememberSaveable { mutableStateOf("moderate") }
    var pain by rememberSaveable { mutableStateOf("a_little") }
    var mood by rememberSaveable { mutableStateOf("slightly_off") }
    var note by rememberSaveable { mutableStateOf("") }

    JournalDialogFrame(
        title = "Daily check-in",
        subtitle = uiState.dailyCheckInStatus?.prompt?.questionText
            ?.takeIf(String::isNotBlank)
            ?: "How did today feel?",
        isLoading = uiState.isLoadingJournal,
        isSubmitting = uiState.isSubmittingJournal,
        canSubmit = uiState.dailyCheckInStatus != null,
        onDismiss = onDismiss,
        onSubmit = {
            onSubmit(compared, energy, usableEnergy, systemLoad, pain, mood, note)
        },
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 470.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            TextChoiceGroup(
                title = "Compared with yesterday",
                choices = listOf("Better" to "better", "About the same" to "same", "Worse" to "worse"),
                selected = compared,
                onSelected = { compared = it },
            )
            TextChoiceGroup(
                title = "Energy",
                choices = listOf("Good" to "good", "Manageable" to "manageable", "Low" to "low", "Depleted" to "depleted"),
                selected = energy,
                onSelected = { energy = it },
            )
            TextChoiceGroup(
                title = "Usable energy",
                choices = listOf("Plenty" to "plenty", "Enough" to "enough", "Limited" to "limited", "Very limited" to "very_limited"),
                selected = usableEnergy,
                onSelected = { usableEnergy = it },
            )
            TextChoiceGroup(
                title = "System load",
                choices = listOf("Light" to "light", "Moderate" to "moderate", "Heavy" to "heavy", "Overwhelming" to "overwhelming"),
                selected = systemLoad,
                onSelected = { systemLoad = it },
            )
            TextChoiceGroup(
                title = "Pain",
                choices = listOf("None" to "none", "A little" to "a_little", "Noticeable" to "noticeable", "Strong" to "strong"),
                selected = pain,
                onSelected = { pain = it },
            )
            TextChoiceGroup(
                title = "Mood",
                choices = listOf("Calm" to "calm", "Slightly off" to "slightly_off", "Noticeable" to "noticeable", "Strong" to "strong"),
                selected = mood,
                onSelected = { mood = it },
            )
            JournalNoteField(note = note, onNoteChanged = { note = it })
        }
    }
}

@Composable
private fun JournalDialogFrame(
    title: String,
    subtitle: String,
    isLoading: Boolean,
    isSubmitting: Boolean,
    canSubmit: Boolean,
    onDismiss: () -> Unit,
    onSubmit: () -> Unit,
    content: @Composable () -> Unit,
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            colors = CardDefaults.cardColors(containerColor = GaiaPanel),
            border = BorderStroke(1.dp, GaiaBlue.copy(alpha = 0.25f)),
            shape = RoundedCornerShape(28.dp),
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 760.dp),
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.Top,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = title,
                            color = Color.White,
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = subtitle,
                            color = Color(0xFFADB7C5),
                            fontSize = 14.sp,
                            lineHeight = 20.sp,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                    TextButton(onClick = onDismiss, enabled = !isSubmitting) {
                        Text("Close")
                    }
                }
                if (isLoading) {
                    Spacer(modifier = Modifier.height(20.dp))
                    CircularProgressIndicator(
                        color = GaiaBlue,
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                    )
                    Spacer(modifier = Modifier.height(20.dp))
                } else {
                    content()
                    Button(
                        onClick = onSubmit,
                        enabled = canSubmit && !isSubmitting,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = GaiaBlue,
                            contentColor = GaiaNavy,
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                color = GaiaNavy,
                                strokeWidth = 2.dp,
                                modifier = Modifier.height(20.dp),
                            )
                        } else {
                            Text("Save", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SelectableJournalRow(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (selected) GaiaBlue.copy(alpha = 0.22f) else Color.White.copy(alpha = 0.05f),
        ),
        border = BorderStroke(
            1.dp,
            if (selected) GaiaBlue else Color.White.copy(alpha = 0.08f),
        ),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Text(
            text = label,
            color = if (selected) GaiaBlue else Color.White,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 13.dp),
        )
    }
}

@Composable
private fun JournalChoiceGroup(
    title: String,
    choices: List<Pair<String, Int>>,
    selected: Int,
    onSelected: (Int) -> Unit,
) {
    Text(
        text = title,
        color = Color(0xFFADB7C5),
        fontSize = 13.sp,
        fontWeight = FontWeight.Bold,
    )
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(choices) { choice ->
            JournalChoiceChip(
                label = choice.first,
                selected = choice.second == selected,
                onClick = { onSelected(choice.second) },
            )
        }
    }
}

@Composable
private fun TextChoiceGroup(
    title: String,
    choices: List<Pair<String, String>>,
    selected: String,
    onSelected: (String) -> Unit,
) {
    Text(
        text = title,
        color = Color(0xFFADB7C5),
        fontSize = 13.sp,
        fontWeight = FontWeight.Bold,
    )
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(choices) { choice ->
            JournalChoiceChip(
                label = choice.first,
                selected = choice.second == selected,
                onClick = { onSelected(choice.second) },
            )
        }
    }
}

@Composable
private fun JournalChoiceChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (selected) GaiaBlue.copy(alpha = 0.22f) else Color.White.copy(alpha = 0.05f),
        ),
        border = BorderStroke(
            1.dp,
            if (selected) GaiaBlue else Color.White.copy(alpha = 0.08f),
        ),
        shape = RoundedCornerShape(18.dp),
        modifier = Modifier.clickable(onClick = onClick),
    ) {
        Text(
            text = label,
            color = if (selected) GaiaBlue else Color.White,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
        )
    }
}

@Composable
private fun JournalNoteField(
    note: String,
    onNoteChanged: (String) -> Unit,
) {
    OutlinedTextField(
        value = note,
        onValueChange = onNoteChanged,
        label = { Text("Optional note") },
        minLines = 2,
        maxLines = 3,
        modifier = Modifier.fillMaxWidth(),
    )
}

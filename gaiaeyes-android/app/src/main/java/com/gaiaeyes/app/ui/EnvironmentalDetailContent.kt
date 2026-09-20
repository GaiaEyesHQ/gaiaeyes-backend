package com.gaiaeyes.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gaiaeyes.app.data.ExploreSnapshot
import java.time.Instant
import kotlinx.coroutines.delay

private val EnvironmentalBlue = Color(0xFF7BDDF5)
private val EnvironmentalMuted = Color(0xFFB7C0CC)

/** Shared by the actual Explore destination and the offline UI harness. */
@Composable
internal fun EnvironmentalDetailContent(detail: ExploreDetail, snapshot: ExploreSnapshot?, isLoading: Boolean) {
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) { while (true) { now = Instant.now(); delay(60_000) } }
    val panel = environmentalPanel(detail, snapshot, now)
    if (isLoading) {
        Text("Refreshing sources…", color = EnvironmentalBlue, modifier = Modifier.padding(top = 12.dp))
        LinearProgressIndicator(modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
    }
    panel.readings.forEach { reading ->
        Spacer(Modifier.height(16.dp))
        EnvironmentalCard(reading.title) {
            Text(reading.status, color = if (reading.status == "Current") EnvironmentalBlue else Color(0xFFF1C66D), fontWeight = FontWeight.SemiBold)
            if (reading.metrics.isEmpty()) Text("No readings are available from this source yet.", color = EnvironmentalMuted)
            reading.metrics.forEach { (label, value) ->
                Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text(label, color = EnvironmentalMuted, fontSize = 13.sp)
                    Text(value, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                }
            }
            Text("Observed: ${environmentalTime(reading.timestamp)}", color = EnvironmentalMuted, fontSize = 12.sp)
            Text("Source: ${reading.source}", color = EnvironmentalMuted, fontSize = 12.sp)
            reading.note?.let { Text(it, color = EnvironmentalMuted, fontSize = 13.sp, lineHeight = 19.sp) }
        }
    }
    panel.charts.forEach { chart ->
        Spacer(Modifier.height(16.dp))
        EnvironmentalCard(chart.title) { EnvironmentalHistoryChart(chart) }
    }
    Spacer(Modifier.height(16.dp))
    Text("Freshness follows observation time, not the time you refresh. Gaps in a trend indicate missing samples.", color = EnvironmentalMuted, fontSize = 12.sp, lineHeight = 18.sp)
}

@Composable
private fun EnvironmentalCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF142638)), shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, color = Color.White, fontSize = 19.sp, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun EnvironmentalHistoryChart(chart: EnvironmentalChart) {
    Text(chart.status, color = if (chart.status == "Current") EnvironmentalBlue else Color(0xFFF1C66D), fontSize = 13.sp)
    val points = chart.points
    if (points.isEmpty()) {
        Text("No history samples available. Other readings can still be viewed.", color = EnvironmentalMuted)
    } else {
        val min = points.minOf { requireNotNull(it.v) }
        val max = points.maxOf { requireNotNull(it.v) }
        val last = requireNotNull(points.last().v)
        Text("Latest ${environmentalNumber(last, chart.unit)}", color = Color.White, fontWeight = FontWeight.SemiBold)
        Text("Range ${environmentalNumber(min)} – ${environmentalNumber(max, chart.unit)} · ${points.size} samples", color = EnvironmentalMuted, fontSize = 12.sp)
        val start = requireNotNull(environmentalInstant(points.first().t)).toEpochMilli()
        val end = requireNotNull(environmentalInstant(points.last().t)).toEpochMilli()
        val span = (end - start).coerceAtLeast(1).toDouble()
        val valueSpan = (max - min).takeIf { it > 0 } ?: 1.0
        Canvas(Modifier.fillMaxWidth().height(140.dp).semantics {
            contentDescription = "${chart.title}. ${points.size} samples. Minimum $min, maximum $max, latest $last ${chart.unit}. ${chart.status}."
        }) {
            val inset = 6.dp.toPx()
            fun position(index: Int): Offset {
                val point = points[index]
                val x = inset + ((requireNotNull(environmentalInstant(point.t)).toEpochMilli() - start) / span).toFloat() * (size.width - 2 * inset)
                val normalized = if (max == min) .5 else (requireNotNull(point.v) - min) / valueSpan
                return Offset(x, size.height - inset - normalized.toFloat() * (size.height - 2 * inset))
            }
            for (i in 0..2) {
                val y = inset + i * (size.height - 2 * inset) / 2
                drawLine(Color.White.copy(alpha = .12f), Offset(inset, y), Offset(size.width - inset, y))
            }
            for (i in points.indices) {
                if (i > 0) {
                    val gap = requireNotNull(environmentalInstant(points[i].t)).epochSecond - requireNotNull(environmentalInstant(points[i - 1].t)).epochSecond
                    if (gap <= chart.maxGapMinutes * 60) drawLine(EnvironmentalBlue, position(i - 1), position(i), strokeWidth = 2.dp.toPx())
                }
                drawCircle(EnvironmentalBlue, if (points.size < 30) 2.5.dp.toPx() else 1.dp.toPx(), position(i))
            }
        }
        Text("From ${environmentalTime(points.first().t)}\nTo ${environmentalTime(points.last().t)}", color = EnvironmentalMuted, fontSize = 12.sp, lineHeight = 18.sp)
        if (points.size == 1) Text("One observation; more samples are needed for a trend.", color = EnvironmentalMuted, fontSize = 12.sp)
    }
    Text("Source: ${chart.source}", color = EnvironmentalMuted, fontSize = 12.sp)
}

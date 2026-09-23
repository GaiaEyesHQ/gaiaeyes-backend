package com.gaiaeyes.app.visualharness

import android.content.Intent
import android.graphics.Bitmap
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

class PollenAvailabilityScreenTest {
 @get:Rule val compose=createEmptyComposeRule()
 private val instrumentation=InstrumentationRegistry.getInstrumentation()
 private var scenario:ActivityScenario<IsolatedMainAppActivity>?=null
 @After fun close(){scenario?.close()}
 private fun click(text:String){compose.onAllNodesWithText(text).onLast().performClick();compose.waitForIdle()}
 private fun frame(text:String){
  val node=compose.onAllNodesWithText(text).onFirst();node.performScrollTo()
  val top=node.fetchSemanticsNode().boundsInRoot.top
  compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.VerticalScrollAxisRange)).onFirst()
   .performSemanticsAction(SemanticsActions.ScrollBy){it(0f,top-80f)}
  compose.waitForIdle()
 }
 private fun launch(allergens:JSONObject,forecast:JSONObject?=null,large:Boolean=false){
  val klass=if(large) IsolatedMainAppLargeFontActivity::class.java else IsolatedMainAppActivity::class.java
  scenario=ActivityScenario.launch(Intent(instrumentation.targetContext,klass).putExtra("g037",true))
  compose.waitUntil(20000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.drivers?.drivers?.drivers?.size==5};ready}
  click("Explore")
  compose.waitUntil(20000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeather?.local!=null && !it.fixture.viewModel.uiState.value.isLoadingExplore};ready}
  val body=JSONObject(instrumentation.targetContext.assets.open("g037-local.json").bufferedReader().readText())
  body.put("allergens",allergens);body.getJSONObject("air").put("aqi",47).put("category","Good")
  if(forecast!=null)body.put("forecast_daily",org.json.JSONArray().put(forecast))
  scenario!!.onActivity{it.fixture.server.readOverrides["/v1/local/check"]=Reply(body=body.toString());it.fixture.viewModel.refreshLocalWeather()}
  compose.waitUntil(10000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeather?.local?.air?.aqi==47 && !it.fixture.viewModel.uiState.value.isLoadingLocalWeather};ready}
  compose.onAllNodesWithText("Local Conditions").onFirst().performScrollTo();click("Local Conditions")
 }
 private fun capture(name:String){
  compose.waitForIdle();instrumentation.waitForIdleSync();android.os.SystemClock.sleep(350)
  val dir=File(instrumentation.targetContext.filesDir,"g048").apply{mkdirs()}
  val bitmap=requireNotNull(instrumentation.uiAutomation.takeScreenshot())
  File(dir,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
  File(dir,"$name-semantics.txt").writeText(compose.onRoot().printToString())
  scenario!!.onActivity{
   assertEquals(47,it.fixture.viewModel.uiState.value.localWeather?.local?.air?.aqi)
   assertEquals(0,it.fixture.server.mutations)
   File(dir,"$name-ledger.json").writeText(it.fixture.ledger().toString())
  }
 }
 @Test fun emptyResponseExplainedWhileWeatherRemainsAvailable(){
  launch(JSONObject());frame("Allergens")
  compose.onNodeWithText("No pollen readings are available for this location in this update. Missing data does not mean a low pollen level.").assertIsDisplayed()
  capture("empty-pollen")
  frame("Air quality");compose.onNodeWithText("47 AQI").assertExists();capture("retained-air-quality")
 }
 @Test fun categoryZeroAndDatedForecastRenderWithoutPromotingForecast(){
  val now=Instant.now().toString();val day=LocalDate.now(ZoneOffset.UTC)
  launch(JSONObject().put("overall_level","high").put("grass_level","moderate").put("weed_index",0)
   .put("forecast_day",day.toString()).put("source","google-pollen:forecast").put("updated_at",now),
   JSONObject().put("day",day.plusDays(1).toString()).put("temp_high_c",30).put("pollen_overall_index",3)
    .put("pollen_grass_index",3).put("pollen_weed_index",0).put("pollen_source","google-pollen:forecast").put("pollen_updated_at",now))
  frame("Allergens");compose.onAllNodesWithText("High").onFirst().assertExists();val layouts=mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
  compose.onNodeWithText("Moderate").performSemanticsAction(SemanticsActions.GetTextLayoutResult){it(layouts)}
  assertEquals("Category should fit without a mid-word wrap",1,layouts.single().lineCount)
  capture("category-only")
  frame("Weed");compose.onNodeWithText("0 / 5").assertIsDisplayed();capture("zero-is-not-missing")
  frame("Daily forecast");compose.onNode(hasText("Pollen forecast (",substring=true)).assertExists();capture("dated-pollen-forecast")
 }
 @Test fun largeTextKeepsHistoricalPollenClearlyDated(){
  launch(JSONObject().put("overall_index",3).put("grass_index",3).put("source","google-pollen:forecast")
   .put("forecast_day","2026-01-01").put("updated_at","2026-01-01T01:00:00Z"),large=true)
  frame("Allergens");compose.onNode(hasText("Not today's pollen forecast.",substring=true)).assertExists();capture("large-historical-pollen")
  frame("Last reported");compose.onAllNodesWithText("3 / 5").onFirst().assertIsDisplayed();capture("large-last-reported")
 }
}

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
import org.json.JSONArray
import org.junit.*
import org.junit.Assert.*
import java.io.File
import java.time.Instant

class ForecastParityScreenTest {
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
 private fun days(count:Int)=JSONArray().apply {
  val now=Instant.now().toString()
  repeat(count){i->put(JSONObject().put("day","2026-09-${22+i}").put("temp_high_c",30+i).put("temp_low_c",20)
   .put("condition_summary",if(i==0)"Partly cloudy" else "Sunny").put("source","nws:forecast-hourly").put("issued_at",now)
   .apply {
    if(i==0){put("temp_delta_from_prior_day_c",2);put("wind_speed",8);put("wind_gust",20);put("aqi_forecast",52)
     put("pollen_overall_index",3);put("pollen_grass_index",0);put("pollen_source","google-pollen:forecast");put("pollen_updated_at",now)}
    if(i==1){put("temp_delta_from_prior_day_c",0);put("wind_speed",0);put("wind_gust",0);put("aqi_forecast",0)}
    if(i==6){put("temp_delta_from_prior_day_c",-2);put("wind_gust",12);put("source","unidentified-provider")}
   })}
 }
 private fun setForecast(rows:JSONArray){
  val body=JSONObject(instrumentation.targetContext.assets.open("g037-local.json").bufferedReader().readText())
  body.put("forecast_daily",rows);body.put("allergens",JSONObject());body.getJSONObject("air").put("aqi",47).put("category","Good")
  scenario!!.onActivity{it.fixture.server.readOverrides["/v1/local/check"]=Reply(body=body.toString());it.fixture.viewModel.refreshLocalWeather()}
  compose.waitUntil(10000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeather?.local?.air?.aqi==47 && it.fixture.viewModel.uiState.value.localWeather?.local?.forecastDaily?.size==rows.length() && !it.fixture.viewModel.uiState.value.isLoadingLocalWeather};ready}
 }
 private fun launch(rows:JSONArray,large:Boolean=false){
  val klass=if(large)IsolatedMainAppLargeFontActivity::class.java else IsolatedMainAppActivity::class.java
  scenario=ActivityScenario.launch(Intent(instrumentation.targetContext,klass).putExtra("g037",true))
  compose.waitUntil(20000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.drivers?.drivers?.drivers?.size==5};ready}
  click("Explore")
  compose.waitUntil(20000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeather?.local!=null && !it.fixture.viewModel.uiState.value.isLoadingExplore};ready}
  setForecast(rows);compose.onAllNodesWithText("Local Conditions").onFirst().performScrollTo();click("Local Conditions")
 }
 private fun capture(name:String){
  compose.waitForIdle();instrumentation.waitForIdleSync();android.os.SystemClock.sleep(250)
  val dir=File(instrumentation.targetContext.filesDir,"g050").apply{mkdirs()}
  val bitmap=requireNotNull(instrumentation.uiAutomation.takeScreenshot())
  File(dir,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
  File(dir,"$name-semantics.txt").writeText(compose.onRoot().printToString())
  scenario!!.onActivity{assertEquals(0,it.fixture.server.mutations);assertEquals(47,it.fixture.viewModel.uiState.value.localWeather?.local?.air?.aqi)
   File(dir,"$name-ledger.json").writeText(it.fixture.ledger().toString())}
 }
 private fun expansionJourney(large:Boolean){
  launch(days(8),large)
  compose.onNodeWithText("Fri, Sep 25").assertDoesNotExist();compose.onNodeWithText("Tue, Sep 29").assertDoesNotExist()
  frame("Daily forecast");compose.onNode(hasText("+3.6°F vs prior day",substring=true)).assertExists()
  compose.onNode(hasText("Gust 20 km/h",substring=true)).assertExists()
  compose.onNode(hasText("Forecast AQI 52",substring=true)).assertExists()
  compose.onNode(hasText("Pollen forecast (2026-09-22 UTC): 3 / 5, Grass 0 / 5",substring=true)).assertExists()
  val prefix=if(large)"large" else "normal";capture("$prefix-three-days")
  frame("Show all 7 days")
  compose.onNodeWithText("Show all 7 days").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"Collapsed"))
  compose.onNodeWithText("Showing 3 of 7 days").assertExists();capture("$prefix-expand-control");click("Show all 7 days")
  compose.onNodeWithText("Fri, Sep 25").assertExists();compose.onNodeWithText("Mon, Sep 28").assertExists();compose.onNodeWithText("Tue, Sep 29").assertDoesNotExist()
  frame("Mon, Sep 28");compose.onNode(hasText("Gust 12 (unit unavailable)",substring=true)).assertExists();capture("$prefix-seven-days-end")
  frame("Show fewer days");compose.onNodeWithText("Show fewer days").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"Expanded"));click("Show fewer days")
  compose.onNodeWithText("Fri, Sep 25").assertDoesNotExist();compose.onNodeWithText("Daily forecast").assertIsDisplayed();capture("$prefix-collapsed")
  frame("Allergens");compose.onNode(hasText("Missing data does not mean a low pollen level.",substring=true)).assertExists()
  if(!large){frame("Air quality");capture("normal-retained-air-pollen");frame("Close");click("Close");compose.onAllNodesWithText("Explore").onFirst().assertExists()}
 }
 @Test fun ordinaryForecastExpandsAndCollapsesWithoutChangingData(){expansionJourney(false)}
 @Test fun largeForecastKeepsFieldsAndExpansionAccessible(){expansionJourney(true)}
 @Test fun fewerThanFourDaysAndEmptyForecastNeedNoExpansion(){
  launch(days(2));frame("Daily forecast");compose.onNodeWithText("Show all 2 days").assertDoesNotExist()
  compose.onNode(hasText("Forecast AQI 0",substring=true)).assertExists();capture("two-available-days")
  setForecast(JSONArray());frame("Daily forecast");compose.onNodeWithText("Forecast unavailable. Other local readings remain available.").assertIsDisplayed()
  compose.onNodeWithText("Tue, Sep 22").assertDoesNotExist();capture("empty-forecast")
 }
}

package com.gaiaeyes.app.visualharness
import android.content.Intent
import android.graphics.Bitmap
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import kotlinx.coroutines.runBlocking
import java.io.File
import org.junit.*
import org.junit.Assert.*

class LocalConditionsParityScreenTest {
 @get:Rule val compose=createEmptyComposeRule()
 private val instrumentation=InstrumentationRegistry.getInstrumentation()
 private var scenario: ActivityScenario<IsolatedMainAppActivity>?=null
 @After fun close(){scenario?.close()}
 private fun launch(large:Boolean=false){
  val klass=if(large) IsolatedMainAppLargeFontActivity::class.java else IsolatedMainAppActivity::class.java
  scenario=ActivityScenario.launch(Intent(instrumentation.targetContext,klass).putExtra("g037",true))
  compose.waitUntil(20000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.drivers?.drivers?.drivers?.size==5};ready}
  compose.waitForIdle()
 }
 private fun show(text:String){compose.onAllNodesWithText(text).onFirst().performScrollTo().assertIsDisplayed()}
 private fun frame(text:String){
  val node=compose.onAllNodesWithText(text).onFirst();node.performScrollTo()
  val top=node.fetchSemanticsNode().boundsInRoot.top
  compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.VerticalScrollAxisRange)).onFirst()
    .performSemanticsAction(SemanticsActions.ScrollBy){it(0f,top-80f)}
  compose.waitForIdle()
 }
 private fun click(text:String){compose.onAllNodesWithText(text).onLast().performClick();compose.waitForIdle()}
 private fun assertTextFits(text:String) {
  val results=mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
  compose.onAllNodesWithText(text,useUnmergedTree=true).onFirst().performSemanticsAction(SemanticsActions.GetTextLayoutResult){it(results)}
  File(instrumentation.targetContext.filesDir,"g037/text-layout.txt").writeText(results.joinToString("\n") { "${it.layoutInput.text.text}: size=${it.size}, widthOverflow=${it.didOverflowWidth}, heightOverflow=${it.didOverflowHeight}, paragraphHeight=${it.multiParagraph.height}, constraints=${it.layoutInput.constraints}, style=${it.layoutInput.style}" })
  val matching = results.filter { it.layoutInput.text.text == text };assertTrue(matching.isNotEmpty());assertFalse("Clipped text: $text",matching.any{it.hasVisualOverflow})
 }
 private fun capture(name:String){
  compose.waitForIdle();instrumentation.waitForIdleSync();android.os.SystemClock.sleep(350)
  val dir=File(instrumentation.targetContext.filesDir,"g037").apply{mkdirs()}
  val bitmap=requireNotNull(instrumentation.uiAutomation.takeScreenshot())
  File(dir,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
  File(dir,"$name-semantics.txt").writeText(compose.onRoot().printToString())
  scenario?.onActivity{File(dir,"$name-ledger.json").writeText(it.fixture.ledger().toString())}
 }
 private fun tour(prefix:String){
  capture("${prefix}home")
  frame("Signals to Watch");capture("${prefix}home-drivers")
  click("Explore");compose.waitUntil(10000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeather?.local!=null && !it.fixture.viewModel.uiState.value.isLoadingExplore};ready};capture("${prefix}explore-errors");show("Dismiss");click("Dismiss");frame("Explore the signals around you.");capture("${prefix}explore");frame("Local Conditions");assertTextFits("1011.5 hPa");capture("${prefix}explore-local");show("Explore the signals around you.")
  show("View all drivers ›");click("View all drivers ›")
  frame("Air Quality");capture("${prefix}drivers-aqi")
  compose.onNodeWithText("Moderate").assertExists()
  compose.onNode(hasText("matches what you asked Gaia Eyes to track",substring=true)).assertDoesNotExist()
  show("Why included");compose.onAllNodesWithText("Why included").onFirst().performClick();frame("Included in your tracking preferences.");capture("${prefix}drivers-context")
  show("Back");click("Back");show("Local Conditions");click("Local Conditions")
  capture("${prefix}local")
  frame("Air quality");capture("${prefix}local-air")
  frame("Allergens");capture("${prefix}local-allergens")
  frame("Weed");compose.onNodeWithText("0 / 5").assertExists();capture("${prefix}local-pollen-types")
  frame("Daily forecast");capture("${prefix}local-forecast");frame("Moon");capture("${prefix}local-moon")
  show("Close");click("Close")
  scenario!!.onActivity { f ->
   val requests=f.fixture.server.requests.toList()
   assertTrue(requests.any{it.startsWith("GET /v1/users/me/drivers synthetic-")})
   assertTrue(requests.any{it=="GET /v1/local/check public"})
   assertEquals(0,f.fixture.server.mutations)
   assertNotNull(f.fixture.viewModel.uiState.value.localWeather?.local)
   // Unavailable unrelated Explore feeds cannot prevent local weather/Drivers from rendering.
   assertEquals(5,f.fixture.viewModel.uiState.value.drivers?.drivers?.drivers?.size)
  }
 }
 @Test fun retainedUlfRegionalAndHistoryViews() {
  ActivityScenario.launch<IsolatedEnvironmentalActivity>(Intent(instrumentation.targetContext,IsolatedEnvironmentalActivity::class.java).putExtra("detail","ULF")).use {
   frame("Regional geomagnetic activity");capture("ulf-regional")
   compose.onNode(hasContentDescription("Regional intensity · 48 hours",substring=true)).performScrollTo().assertIsDisplayed()
   capture("ulf-history")
  }
 }
 @Test fun upstreamAbsenceAndRefreshFailureKeepSiblingData() {
  launch();click("Explore")
  scenario!!.onActivity { it.fixture.server.readOverrides["/v1/local/check"]=Reply(body="""{"where":{"zip":"78754"},"weather":{"temp_c":30,"obs_time":"2026-09-19T10:00:00Z"},"air":{"aqi":47,"category":"Good"},"allergens":{},"asof":"2026-09-19T10:00:00Z"}""");it.fixture.viewModel.refreshLocalWeather() }
  compose.waitUntil(10000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeather?.local?.air?.aqi==47};ready}
  show("Local Conditions");click("Local Conditions");frame("Allergens");capture("missing-allergens")
  compose.onAllNodesWithText("Unavailable").onFirst().assertExists()
  scenario!!.onActivity{it.fixture.server.readOverrides["/v1/local/check"]=Reply(503,"{}");it.fixture.viewModel.refreshLocalWeather()}
  compose.waitUntil(10000){var ready=false;scenario!!.onActivity{ready=it.fixture.viewModel.uiState.value.localWeatherMessage?.contains("Showing saved")==true};ready}
  show("Close");capture("failed-refresh-retains-local")
  scenario!!.onActivity{assertEquals(47,it.fixture.viewModel.uiState.value.localWeather?.local?.air?.aqi);assertEquals(5,it.fixture.viewModel.uiState.value.drivers?.drivers?.drivers?.size)}
 }
 @Test fun protectedDriverUnauthorizedMapsToCurrentAccountSignOut() {
  launch()
  var fixture: MainAppFixture?=null;scenario!!.onActivity{fixture=it.fixture;it.fixture.server.readOverrides["/v1/users/me/drivers"]=Reply(401,"{}")}
  val f=fixture!!;val result=runCatching{runBlocking{f.home.refreshDrivers(f.auth.accountA)}}
  assertTrue(result.exceptionOrNull() is ApiUnauthorizedException);assertEquals(1,f.auth.signOuts);assertNull(f.auth.currentAccountId())
 }
 @Test fun actualAppNormalTextAndProtectedRequests(){launch();tour("normal-")}
 @Test fun actualAppLargeTextAndNativeNavigation(){launch(true);tour("large-")}
}

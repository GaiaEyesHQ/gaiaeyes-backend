package com.gaiaeyes.app.ui
import com.gaiaeyes.app.core.network.*
import com.gaiaeyes.app.data.*
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant
class LocalConditionsParityTest {
 private val json = Json { ignoreUnknownKeys = true }
 private fun snapshot(local: LocalCheckResponse) = LocalWeatherSnapshot(ProfileLocation(zip="78754"),local,HomeContextSource.NETWORK,0)
 @Test fun contractKeepsPollenScaleSourceCategoryZeroAndMissing() {
  val local=json.decodeFromString<LocalCheckResponse>("""{"weather":{"temp_c":36},"air":{"aqi":52,"category":"Moderate"},"allergens":{"overall_index":3,"overall_level":"high","overall_label":"Elevated","primary_label":"Grass pollen","tree_index":1,"grass_index":3,"weed_index":0,"mold_index":null,"source":"google-pollen:forecast","updated_at":"2026-09-20T20:00:00Z","relevance_score":5}}""")
  val sections=localConditionSections(snapshot(local)); val a=sections[3]
  assertEquals("96.8°F",sections[0].metrics.first().value); assertEquals("52 AQI",sections[2].metrics.single().value)
  assertEquals("3 / 5",a.metrics.first().value); assertTrue(a.metrics.first().detail!!.contains("High"))
  assertEquals("0 / 5",a.metrics.first{it.label=="Weed"}.value); assertFalse(a.metrics.any{it.label=="Mold"})
  assertTrue(a.detail.contains("google-pollen:forecast")); assertTrue(a.detail.contains("0–5")); assertTrue(a.detail.contains("Forecast, not a direct observation"))
 }
 @Test fun missingAndInvalidValuesDoNotEraseSiblingReadings() {
  val local=LocalCheckResponse(weather=LocalWeather(temperatureC=0.0,humidityPercent=101.0,precipitationProbabilityPercent=Double.NaN,pressureHpa=0.0),air=LocalAir(52),allergens=LocalAllergens(overallIndex=8.0,grassIndex=-1.0))
  val s=localConditionSections(snapshot(local))
  assertEquals("32°F",s[0].metrics.first().value); assertEquals("Unavailable",s[0].metrics[1].value)
  assertEquals("Unavailable",s[1].metrics.single().value); assertEquals("52 AQI",s[2].metrics.single().value)
  assertTrue(s[3].metrics.isEmpty()); assertEquals(0,localConditionSections(snapshot(LocalCheckResponse()))[3].metrics.size)
 }
 @Test fun observationTimeIsIndependentOfTransportAndWeatherSibling() {
  val s=snapshot(LocalCheckResponse(weather=LocalWeather(observationTime="2026-09-20T20:00:00Z"),asof="2026-09-20T20:01:00Z"))
  assertEquals("Fetched",localWeatherSourceLabel(s)); assertTrue(localConditionSections(s)[2].detail.contains("Observation time and source not supplied"))
  val now=Instant.parse("2026-09-20T20:30:00Z")
  assertFalse(localTimestampText("2026-09-20T20:00:00Z","Updated",now)!!.contains("Stale"))
  assertTrue(localTimestampText("2026-09-19T20:00:00Z","Updated",now)!!.contains("Stale")); assertNull(localTimestampText("invalid","Updated",now))
 }
 @Test fun forecastUsesServerFieldsAndLocalCalendarDate() {
  val l=json.decodeFromString<LocalCheckResponse>("""{"forecast_daily":[{"day":"2026-09-20","temp_high_c":35.6,"temp_low_c":23.3,"precip_probability":8,"condition_summary":"Mostly Sunny","humidity_avg":63.2,"wind_speed":8,"source":"nws:forecast-hourly","issued_at":"2026-09-20T10:00:00Z"},{"day":"invalid"}]}""")
  val row=localForecastMetrics(snapshot(l)).single(); assertEquals("Sun, Sep 20",row.label); assertTrue(row.value.contains("High 96.1°F")); assertTrue(row.detail!!.contains("Rain 8%")); assertTrue(row.detail!!.contains("Mostly Sunny")); assertTrue(row.detail!!.contains("Wind 8 km/h")); assertTrue(row.detail!!.contains("Humidity 63%"))
 }
 @Test fun chosenModerateAqiNeverBecomesActiveAndPreferencesStaySeparate() {
  val generic="Air Quality is worth watching because it matches what you asked Gaia Eyes to track."
  val d=json.decodeFromString<DriverItem>("""{"key":"aqi","reading":"52 AQI","reading_value":52,"reading_unit":"AQI","state":"active","state_label":"Active","short_reason":"$generic","personal_reason":"$generic","active_now_text":"AQI is currently 52.","source_hint":"EPA AirNow","updated_at":"2026-09-20T20:00:00Z"}""")
  assertEquals("Moderate",driverConditionLabel(d)); assertEquals("AQI is currently 52.",driverDisplayReason(d)); assertEquals("Included in your tracking preferences.",driverPersonalContext(d)); assertTrue(driverProvenance(d).contains("EPA AirNow"))
  assertEquals("Moderate",driverConditionLabel(d.copy(readingValue=null))); assertEquals("Unavailable",driverConditionLabel(d.copy(reading="N/A",readingValue=null)))
  assertEquals("Tracked",driverConditionLabel(d.copy(key="pressure",reading="-2.4 hPa"))); assertEquals("",driverDisplayReason(d.copy(activeNowText=null)))
 }
 @Test fun aqiBoundariesAndSemanticFallback() {
  listOf(0.0 to "Good",50.0 to "Good",51.0 to "Moderate",100.0 to "Moderate",101.0 to "Unhealthy for sensitive groups",151.0 to "Unhealthy",201.0 to "Very unhealthy",301.0 to "Hazardous").forEach{(v,l)->assertEquals(l,aqiCategory(v))}
  assertNull(aqiCategory(-1.0)); assertNull(aqiCategory(Double.NaN))
  val d=json.decodeFromString<DriverItem>("""{"voice_semantic":{"interpretation":{"seed_short_reason":"Pressure fell 2.4 hPa.","seed_personal_reason":"Selected in your profile."}}}""")
  assertEquals("Pressure fell 2.4 hPa.",driverDisplayReason(d)); assertEquals("Selected in your profile.",driverPersonalContext(d))
 }
 @Test fun moonKeepsFractionScaleAndMissingDistinctFromNewMoon() {
  val l=json.decodeFromString<LocalCheckResponse>("""{"moon":{"phase":"Waxing Gibbous","illum":0.667}}""")
  assertEquals("66.7%",localMoonSection(snapshot(l)).metrics[1].value)
  assertEquals("0%",localMoonSection(snapshot(l.copy(moon=LocalMoon("New Moon",0.0)))).metrics[1].value)
  assertEquals("Unavailable",localMoonSection(snapshot(LocalCheckResponse())).metrics[1].value)
 }

}

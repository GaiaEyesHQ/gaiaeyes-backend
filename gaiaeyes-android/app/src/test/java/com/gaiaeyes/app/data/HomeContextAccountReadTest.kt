package com.gaiaeyes.app.data
import com.gaiaeyes.app.core.network.ApiUnauthorizedException
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
class HomeContextAccountReadTest {
 @Test fun sameAccountGetsTokenAndResult()=runBlocking {
  assertEquals(52,readHomeContextForAccount("a",{"a"},{"token-a"},{error("unexpected sign out")}){assertEquals("token-a",it);52})
 }
 @Test fun replacementDuringTokenRefreshCannotIssueRead()=runBlocking {
  var account="a";var reads=0
  val r=runCatching{readHomeContextForAccount("a",{account},{account="b";"token-b"},{}){reads++;52}}
  assertTrue(r.exceptionOrNull() is CancellationException);assertEquals(0,reads)
 }
 @Test fun lateResultCannotBePublished()=runBlocking {
  var account="a";var published=false
  val r=runCatching{readHomeContextForAccount("a",{account},{"token-a"},{}){account="b";52}}
  r.onSuccess{published=true};assertTrue(r.exceptionOrNull() is CancellationException);assertFalse(published)
 }
 @Test fun lateUnauthorizedCannotSignOutReplacementAccount()=runBlocking {
  var account="a";var signOuts=0
  val r=runCatching{readHomeContextForAccount("a",{account},{"token-a"},{signOuts++}){account="b";throw ApiUnauthorizedException()}}
  assertTrue(r.exceptionOrNull() is ApiUnauthorizedException);assertEquals(0,signOuts)
 }
 @Test fun onlyCurrentUnauthorizedSignsOut()=runBlocking {
  var signOuts=0
  runCatching{readHomeContextForAccount("a",{"a"},{"token-a"},{signOuts++}){throw ApiUnauthorizedException()}};assertEquals(1,signOuts)
  runCatching{readHomeContextForAccount("a",{"a"},{"token-a"},{signOuts++}){error("upstream unavailable")}};assertEquals(1,signOuts)
 }
 @Test fun publicLocalResultMustMatchOriginalAccountBeforeCache()=runBlocking {
  assertTrue(runCatching{requireHomeContextAccount("a",{"b"})}.exceptionOrNull() is CancellationException)
 }
}

package com.floorwars.realtime

import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

// Robolectric for the pipeline's org.json and SharedPreferences; the socket is real OkHttp
// against MockWebServer.
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RealtimeClientTest {
    private val server = MockWebServer()
    private val prefs = RealtimePrefs(RuntimeEnvironment.getApplication())
    private val states = LinkedBlockingQueue<String>()
    private val emitted = LinkedBlockingQueue<Long>()
    private val scheduled = LinkedBlockingQueue<Pair<Long, () -> Unit>>()
    private var now = 0L
    private val pipeline = GameEventPipeline(
        prefs,
        emit = { emitted += JSONObject(it).getLong("event_id") },
        onFlip = {}
    )
    private val client = RealtimeClient(
        realtimeHttpClient(),
        lastEventId = { prefs.lastEventId },
        onMessage = pipeline::onMessage,
        onState = { states += it },
        nowMs = { now },
        random = { 0.5 },
        schedule = { delay, task -> scheduled += delay to task }
    )
    private val wsUrl = server.url("/ws").toString().replaceFirst("http", "ws")

    @After
    fun tearDown() {
        client.clear()
        prefs.clear()
        server.shutdown()
    }

    // Server side of one accepted upgrade; it records closes and can send live events.
    private class ServerSide : WebSocketListener() {
        val opened = LinkedBlockingQueue<WebSocket>()
        val closed = LinkedBlockingQueue<Int>()
        var onOpenSend: List<String> = emptyList()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            onOpenSend.forEach { webSocket.send(it) }
            opened += webSocket
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            closed += code
            webSocket.close(code, null)
        }
    }

    private fun accept(vararg replay: String) = ServerSide().also {
        it.onOpenSend = replay.toList()
        server.enqueue(MockResponse().withWebSocketUpgrade(it))
    }

    private fun refuse(code: Int) = server.enqueue(MockResponse().setResponseCode(code))

    private fun awaitState(expected: String) {
        while (true) {
            val s = states.poll(5, TimeUnit.SECONDS) ?: throw AssertionError("no state $expected")
            if (s == expected) return
        }
    }

    private fun nextSchedule() =
        scheduled.poll(5, TimeUnit.SECONDS) ?: throw AssertionError("no reconnect scheduled")

    private fun take(n: Int) = List(n) { emitted.poll(5, TimeUnit.SECONDS) }

    @Test
    fun connectsWithTheBearerHeaderAndSince() {
        prefs.lastEventId = 41
        accept()
        client.configure(wsUrl, "token-1")
        client.hold(Holder.FOREGROUND)
        awaitState("open")
        val request = server.takeRequest(5, TimeUnit.SECONDS)!!
        assertEquals("Bearer token-1", request.getHeader("Authorization"))
        assertEquals("/ws?since=41", request.path)
    }

    @Test
    fun replayThenLiveEventsWithADuplicateDropped() {
        val side = accept(GameEventPipelineTest.flipped(1), GameEventPipelineTest.flipped(2))
        client.configure(wsUrl, "t")
        client.hold(Holder.FOREGROUND)
        val serverSocket = side.opened.poll(5, TimeUnit.SECONDS)!!
        assertEquals(listOf(1L, 2L), take(2))
        // Live: the replayed 2 arrives again (at least once), then 3.
        serverSocket.send(GameEventPipelineTest.flipped(2))
        serverSocket.send(GameEventPipelineTest.flipped(3))
        assertEquals(listOf(3L), take(1))
        assertNull(emitted.poll(300, TimeUnit.MILLISECONDS))
        assertEquals(3L, prefs.lastEventId)
    }

    @Test
    fun reconnectDelaysFollowTheBackoffAndResetAfterSixtySecondsOpen() {
        repeat(8) { refuse(503) }
        client.configure(wsUrl, "t")
        client.hold(Holder.FOREGROUND)
        val delays = mutableListOf<Long>()
        var retry: () -> Unit = {}
        repeat(8) {
            retry()
            val (delay, task) = nextSchedule()
            delays += delay
            retry = task
        }
        // random 0.5 of min(60 s, 1 s * 2^attempt)
        assertEquals(listOf(500L, 1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000), delays)

        // Open for 60 s, then the server goes: the counter starts again.
        val side = accept()
        retry()
        awaitState("open")
        now += RECONNECT_RESET_AFTER_MS
        refuse(503)
        side.opened.poll(5, TimeUnit.SECONDS)!!.close(1001, "restart")
        assertEquals(500L, nextSchedule().first)
    }

    @Test
    fun aConnectionShorterThanSixtySecondsKeepsCounting() {
        refuse(503)
        client.configure(wsUrl, "t")
        client.hold(Holder.FOREGROUND)
        val (first, retry) = nextSchedule()
        assertEquals(500L, first)
        val side = accept()
        retry()
        awaitState("open")
        now += RECONNECT_RESET_AFTER_MS - 1
        side.opened.poll(5, TimeUnit.SECONDS)!!.close(1001, "restart")
        assertEquals(1_000L, nextSchedule().first)
    }

    @Test
    fun a401StopsReconnectingUntilANewToken() {
        refuse(401)
        client.configure(wsUrl, "expired")
        client.hold(Holder.FOREGROUND)
        awaitState("auth_needed")
        // The same token again does not retry.
        client.configure(wsUrl, "expired")
        client.release(Holder.FOREGROUND)
        client.hold(Holder.FOREGROUND)
        assertNull(scheduled.poll(300, TimeUnit.MILLISECONDS))
        assertEquals(1, server.requestCount)
        assertEquals("auth_needed", client.state)

        accept()
        client.configure(wsUrl, "fresh")
        awaitState("open")
        assertEquals(2, server.requestCount)
        server.takeRequest()
        assertEquals("Bearer fresh", server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun theSocketClosesWhenBothHoldersRelease() {
        val side = accept()
        client.configure(wsUrl, "t")
        client.hold(Holder.FOREGROUND)
        client.hold(Holder.SESSION)
        awaitState("open")
        client.release(Holder.FOREGROUND)
        assertNull(side.closed.poll(300, TimeUnit.MILLISECONDS))
        assertEquals("open", client.state)
        client.release(Holder.SESSION)
        assertEquals(1000, side.closed.poll(5, TimeUnit.SECONDS))
        assertEquals("closed", client.state)
        assertTrue(scheduled.isEmpty())
    }

    @Test
    fun clearClosesTheSocketAndForgetsTheToken() {
        val side = accept()
        client.configure(wsUrl, "t")
        client.hold(Holder.FOREGROUND)
        awaitState("open")
        client.clear()
        assertEquals(1000, side.closed.poll(5, TimeUnit.SECONDS))
        client.release(Holder.FOREGROUND)
        client.hold(Holder.FOREGROUND)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun pingIntervalIsThirtySeconds() {
        assertEquals(30_000, realtimeHttpClient().pingIntervalMillis)
    }
}

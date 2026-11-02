package com.floorwars.floorsensors.classifier

import com.floorwars.floorsensors.TraceCsv
import com.floorwars.floorsensors.segmenter.Segmenter
import java.io.File
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

// Trace replay (plan section 10, Week 2): segment and classify every recorded trace, print a confusion matrix.
// Reads only; never writes to fixtures/ or traces/.
class TraceReplayTest {
    // segments: one "VERDICT ascent duration speed steps" entry per segment, printed for misses.
    private class Result(
        val file: String,
        val label: String,
        val predicted: SegmentClass,
        val segments: List<String>
    )

    private val labels =
        listOf("stairs_up", "stairs_down", "elevator_up", "walk_flat", "shake", "blow")

    // Only a climb up scores; stairs_down and the non-climbs must come out as OTHER.
    private fun expected(label: String) = when (label) {
        "stairs_up" -> SegmentClass.STAIRS
        "elevator_up" -> SegmentClass.ELEVATOR
        else -> SegmentClass.OTHER
    }

    // A trace counts as a climb if any of its segments is one; stairs beat elevator.
    private fun traceClass(segments: List<SegmentClass>) = when {
        SegmentClass.STAIRS in segments -> SegmentClass.STAIRS
        SegmentClass.ELEVATOR in segments -> SegmentClass.ELEVATOR
        else -> SegmentClass.OTHER
    }

    // dir is relative to the repo root; Gradle runs unit tests from app/android/app.
    private fun replay(dir: String): List<Result> {
        val folder = File("../../../$dir")
        // file,label,placement,device,floor_range,notes; only notes may hold a quoted comma, and it comes last.
        val rows = folder.resolve("labels.csv").readLines().drop(1).filter { it.isNotBlank() }
            .map { it.split(",", limit = 6) }
            .associateBy { it[0] }
        val files = folder.listFiles { f ->
            f.name.endsWith(".csv") && f.name != "labels.csv"
        }!!.sortedBy { it.name }
        assertTrue("no traces in $dir", files.isNotEmpty())
        assertEquals("$dir: CSV files vs labels.csv rows", rows.keys, files.map { it.name }.toSet())

        val segmenter = Segmenter()
        val classifier = Classifier()
        return files.map { file ->
            val trace = TraceCsv.read(file.readLines())
            val row = rows.getValue(file.name)
            val label = trace.metadata["label"]
            assertEquals("${file.name}: header label vs labels.csv", row[1], label)
            assertEquals(
                "${file.name}: header placement vs labels.csv",
                row[2],
                trace.metadata["placement"]
            )
            assertTrue("${file.name}: unknown label $label", label in labels)
            val segments = segmenter.segment(trace.pressure, trace.steps)
            val described = segments.map {
                "%s %.2f m %.1f s %.3f m/s %d steps".format(
                    Locale.US,
                    classifier.verdict(it),
                    it.ascentM,
                    it.durationS,
                    it.vertSpeedMps,
                    it.steps
                )
            }
            val predicted = traceClass(segments.map { classifier.classify(it) })
            Result(file.name, label!!, predicted, described)
        }
    }

    private fun printMatrix(dir: String, results: List<Result>) {
        val classes = SegmentClass.entries
        val out = StringBuilder("\n")
        out.appendLine("Trace replay: $dir, ${results.size} files")
        out.append("%-12s".format("true label"))
        classes.forEach { out.append("%10s".format(it)) }
        out.appendLine("  expected")
        for (label in labels) {
            out.append("%-12s".format(label))
            for (c in classes) {
                out.append("%10d".format(results.count { it.label == label && it.predicted == c }))
            }
            out.appendLine("  ${expected(label)}")
        }
        out.appendLine("%-12s%16s%16s".format("class", "precision", "recall"))
        for (c in classes) {
            val hits = results.count { it.predicted == c && expected(it.label) == c }
            val precision = ratio(hits, results.count { it.predicted == c })
            val recall = ratio(hits, results.count { expected(it.label) == c })
            out.appendLine("%-12s%16s%16s".format(c, precision, recall))
        }
        for (r in results.filter { it.predicted != expected(it.label) }) {
            val got = "expected ${expected(r.label)}, got ${r.predicted}"
            out.appendLine("miss ${r.file}: $got; ${r.segments}")
        }
        println(out)
    }

    private fun ratio(hits: Int, total: Int): String {
        if (total == 0) return "n/a (0/0)"
        return "%.2f (%d/%d)".format(Locale.US, hits.toDouble() / total, hits, total)
    }

    @Test
    fun syntheticFixtures() {
        // Not evaluation: generated data (fixtures/synthetic/README.md). Shown to catch regressions only.
        printMatrix("fixtures/synthetic", replay("fixtures/synthetic"))
    }

    @Test
    fun realTraces() {
        val results = replay("traces")
        printMatrix("traces", results)
        // The trace-replay gate. Only real data: synthetic numbers are not evaluation.
        val stairs = results.filter { it.predicted == SegmentClass.STAIRS }
        val hits = stairs.count { expected(it.label) == SegmentClass.STAIRS }
        assertTrue("traces/: no trace classified STAIRS", stairs.isNotEmpty())
        assertTrue(
            "traces/: STAIRS precision $hits/${stairs.size} is below $MIN_STAIRS_PRECISION",
            hits.toDouble() / stairs.size >= MIN_STAIRS_PRECISION
        )
    }

    companion object {
        // Points ride on STAIRS; with 3 real stairs traces one false STAIRS gives <= 0.75: CI fails.
        const val MIN_STAIRS_PRECISION = 0.9
    }
}

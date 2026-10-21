package com.floorwars.floorsensors

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PureKotlinPackagesTest {
    @Test
    fun segmenterAndClassifierHaveNoAndroidImports() {
        val forbidden = listOf("import android.", "import androidx.", "import com.facebook.")
        for (pkg in listOf("segmenter", "classifier")) {
            val sources = File("src/main/java/com/floorwars/floorsensors/$pkg")
                .walk()
                .filter { it.extension == "kt" }
                .toList()
            assertTrue("no Kotlin sources found for $pkg", sources.isNotEmpty())
            val offenders = sources.filter { file ->
                file.readLines().any { line -> forbidden.any { line.startsWith(it) } }
            }
            assertEquals("$pkg imports Android or React Native", emptyList<File>(), offenders)
        }
    }
}

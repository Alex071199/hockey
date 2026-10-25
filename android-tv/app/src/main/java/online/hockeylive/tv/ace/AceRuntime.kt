package online.hockeylive.tv.ace

import android.content.Context
import android.os.StatFs
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream

/**
 * Запуск встроенного P2P-движка AceStream (как в aceHub):
 * assets/ace/ace-armeabi-v7a.zip распаковывается в filesDir, нативный раннер
 * libacepython.so (из nativeLibraryDir) исполняет main_android.py.
 * Движок поднимает HTTP API на 127.0.0.1:6878 и telnet API на 62062.
 */
object AceRuntime {

    private const val TAG = "AceEngine"
    private const val ASSET_ZIP = "ace/ace-armeabi-v7a.zip"
    private const val ASSET_MAIN = "ace/main_android.py"
    private const val MARKER = ".prepared-v1"

    const val HTTP_PORT = 6878
    const val API_PORT = 62062

    @Volatile
    private var process: Process? = null

    private val lock = Any()

    fun isProcessAlive(): Boolean {
        val p = process ?: return false
        return try {
            p.exitValue()
            false
        } catch (e: IllegalThreadStateException) {
            true
        }
    }

    private fun rootDir(context: Context) = File(context.filesDir, "aceengine")
    private fun cacheDir(context: Context): File {
        val f = File(context.cacheDir, "aceengine")
        if (!f.exists()) f.mkdirs()
        return f
    }

    /**
     * Распаковывает движок (при первом запуске), стартует процесс и ждёт,
     * пока HTTP API не ответит. Блокирующий — вызывать из IO.
     */
    @Synchronized
    fun ensureStarted(context: Context, onStatus: (String) -> Unit) {
        val app = context.applicationContext
        prepare(app, onStatus)

        if (isProcessAlive() && httpReady()) return

        if (!isProcessAlive()) {
            onStatus("Запуск P2P-движка…")
            start(app)
        }
        waitReady(onStatus)
    }

    private fun prepare(context: Context, onStatus: (String) -> Unit) {
        val root = rootDir(context)
        val marker = File(root, MARKER)
        if (!marker.exists()) {
            onStatus("Установка P2P-движка (первый запуск, ~30 сек)…")
            deleteRecursively(root)
            if (!root.mkdirs() && !root.isDirectory) {
                throw IOException("Cannot create $root")
            }

            val tmpZip = File(cacheDir(context), "ace-engine.zip")
            onStatus("Загрузка движка…")
            copyAsset(context, ASSET_ZIP, tmpZip, onStatus)
            onStatus("Распаковка движка…")
            unzip(tmpZip, root)
            tmpZip.delete()
            if (!marker.createNewFile()) {
                throw IOException("Cannot mark engine prepared")
            }
            Log.i(TAG, "engine unpacked to $root")
        }

        copyAssetSimple(context, ASSET_MAIN, File(root, "main_android.py"))
        File(root, "tmp").mkdirs()
        File(root, "android-data").mkdirs()
        File(cacheDir(context), "tmp").mkdirs()

        writeAndroidInfo(context, root, cacheDir(context), File(root, "android-runtime.json"))
    }

    private fun start(context: Context) {
        val root = rootDir(context)
        val cache = cacheDir(context)

        val runner = File(context.applicationInfo.nativeLibraryDir, "libacepython.so")
        if (!runner.exists()) {
            throw IOException("Отсутствует libacepython.so: ${runner.absolutePath}")
        }
        val mainPy = File(root, "main_android.py")
        if (!mainPy.exists()) {
            throw IOException("Отсутствует main_android.py")
        }

        val command = listOf(
            runner.absolutePath,
            mainPy.absolutePath,
            "--bind-all",
            "--live-cache-type", "memory",
            "--live-mem-cache-size", "104857600",
            "--disable-sentry",
            "--log-stdout",
            "--disable-upnp",
        )
        Log.i(TAG, "starting: $command")

        val pb = ProcessBuilder(command)
        pb.directory(root)
        pb.redirectErrorStream(true)

        val env = pb.environment()
        env["ACE_ROOT"] = root.absolutePath
        env["ACE_CACHE_DIR"] = cache.absolutePath
        env["ACE_ANDROID_INFO"] = File(root, "android-runtime.json").absolutePath
        env["ACESTREAM_HOME"] = root.absolutePath
        env["ANDROID_ROOT"] = "/system"
        env["ANDROID_DATA"] = File(root, "android-data").absolutePath
        env["PYTHONHOME"] = File(root, "python").absolutePath
        env["PYTHONPATH"] = listOf(
            File(root, "python/lib/stdlib").absolutePath,
            File(root, "python/lib/modules").absolutePath,
            File(root, "data").absolutePath,
            File(root, "modules.zip").absolutePath,
            File(root, "eggs-unpacked").absolutePath,
            File(root, "lib").absolutePath,
        ).joinToString(":")
        env["LD_LIBRARY_PATH"] = listOf(
            File(root, "python/lib").absolutePath,
            File(root, "lib").absolutePath,
            File(root, "acestreamengine").absolutePath,
            context.applicationInfo.nativeLibraryDir,
            "/system/lib",
            "/system/lib64",
        ).joinToString(":")
        env["FROZENLIST_NO_EXTENSIONS"] = "1"
        env["MULTIDICT_NO_EXTENSIONS"] = "1"
        env["YARL_NO_EXTENSIONS"] = "1"
        env["TEMP"] = File(root, "tmp").absolutePath
        env["PATH"] = File(root, "python/bin").absolutePath + ":/system/bin"

        val proc = pb.start()
        process = proc

        Thread {
            try {
                proc.inputStream.bufferedReader().useLines { lines ->
                    for (line in lines) {
                        Log.d("AceEngineOut", line)
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "log stream ended: ${e.message}")
            }
        }.apply {
            isDaemon = true
            name = "ace-engine-log"
            start()
        }
    }

    private fun httpReady(): Boolean {
        return try {
            val url = java.net.URL("http://127.0.0.1:$HTTP_PORT/webui/api/service?method=get_version&format=json")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 1500
            conn.readTimeout = 1500
            val code = conn.responseCode
            conn.disconnect()
            code in 200..399
        } catch (e: Exception) {
            false
        }
    }

    private fun waitReady(onStatus: (String) -> Unit) {
        val deadline = System.currentTimeMillis() + 60_000
        var lastReport = 0L
        while (System.currentTimeMillis() < deadline) {
            if (!isProcessAlive()) {
                throw IOException("P2P-движок завершился сразу после запуска")
            }
            if (httpReady()) {
                Log.i(TAG, "engine ready")
                return
            }
            val now = System.currentTimeMillis()
            if (now - lastReport > 3000) {
                val sec = ((60_000 - (deadline - now)) / 1000).toInt()
                onStatus("Запуск P2P-движка… ($sec сек)")
                lastReport = now
            }
            try {
                Thread.sleep(400)
            } catch (e: InterruptedException) {
                Thread.currentThread().interrupt()
                throw IOException("interrupted")
            }
        }
        throw IOException("P2P-движок не запустился за 60 секунд")
    }

    private fun copyAsset(context: Context, assetPath: String, dest: File, onStatus: (String) -> Unit) {
        val parent = dest.parentFile
        if (parent != null && !parent.exists()) parent.mkdirs()
        val totalMb = try {
            context.assets.openFd(assetPath).declaredLength / (1024 * 1024)
        } catch (e: Exception) {
            -1L
        }
        var copied = 0L
        var nextReport = 4L * 1024 * 1024
        context.assets.open(assetPath).use { input ->
            FileOutputStream(dest).use { out ->
                val buf = ByteArray(256 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n <= 0) break
                    out.write(buf, 0, n)
                    copied += n
                    if (totalMb > 0 && copied >= nextReport) {
                        nextReport += 4L * 1024 * 1024
                        onStatus("Загрузка движка… ${copied / (1024 * 1024)}/${totalMb} МБ")
                    }
                }
                out.flush()
            }
        }
    }

    private fun copyAssetSimple(context: Context, assetPath: String, dest: File) {
        val parent = dest.parentFile
        if (parent != null && !parent.exists()) parent.mkdirs()
        context.assets.open(assetPath).use { input ->
            FileOutputStream(dest).use { out ->
                input.copyTo(out)
                out.flush()
            }
        }
    }

    private fun unzip(zipFile: File, destination: File) {
        val destinationPath = destination.canonicalPath + File.separator
        ZipInputStream(java.io.BufferedInputStream(java.io.FileInputStream(zipFile))).use { input ->
            var entry: ZipEntry?
            val buffer = ByteArray(128 * 1024)
            while (input.nextEntry.also { entry = it } != null) {
                val e = entry ?: break
                val target = File(destination, e.name)
                val targetPath = target.canonicalPath
                if (!targetPath.startsWith(destinationPath)) {
                    throw IOException("Unsafe zip entry: ${e.name}")
                }
                if (e.isDirectory) {
                    if (!target.exists() && !target.mkdirs()) throw IOException("Cannot create $target")
                } else {
                    val parent = target.parentFile
                    if (parent != null && !parent.exists() && !parent.mkdirs()) {
                        throw IOException("Cannot create $parent")
                    }
                    BufferedOutputStream(FileOutputStream(target)).use { out ->
                        var n: Int
                        while (input.read(buffer).also { n = it } >= 0) {
                            out.write(buffer, 0, n)
                        }
                    }
                    val name = target.name
                    if (name == "python" || name.endsWith(".so") || name.endsWith(".py") || name.endsWith(".zip")) {
                        target.setExecutable(true, false)
                    }
                }
            }
        }
    }

    private fun deleteRecursively(file: File) {
        if (!file.exists()) return
        if (file.isDirectory) {
            file.listFiles()?.forEach { deleteRecursively(it) }
        }
        file.delete()
    }

    private fun writeAndroidInfo(context: Context, root: File, cache: File, output: File) {
        try {
            val am = context.getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
            val mem = android.app.ActivityManager.MemoryInfo()
            am.getMemoryInfo(mem)
            val cacheStats = StatFs(cache.absolutePath)
            val pInfo = context.packageManager.getPackageInfo(context.packageName, 0)

            val paths = JSONObject()
                .put("aceStreamHome", cache.absolutePath)
                .put("cacheDir", cache.absolutePath)
                .put("logsDir", cache.absolutePath)
                .put("androidDataDir", File(root, "android-data").absolutePath)
                .put("tempDir", File(root, "tmp").absolutePath)

            val memory = JSONObject()
                .put("totalBytes", if (mem.totalMem > 0) mem.totalMem else 64L * 1024 * 1024)
                .put("availableBytes", mem.availMem)
                .put("javaMaxBytes", Runtime.getRuntime().maxMemory())
                .put("memoryClassMb", am.memoryClass)
                .put("lowMemory", mem.lowMemory)

            val storage = JSONObject()
                .put("cacheAvailableBytes", cacheStats.availableBytes)
                .put("cacheTotalBytes", cacheStats.totalBytes)
                .put("cacheBlockSizeBytes", cacheStats.blockSizeLong)
                .put("cacheBlockCount", cacheStats.blockCountLong)
                .put("cacheAvailableBlocks", cacheStats.availableBlocksLong)
                .put("cacheBlockCount", cacheStats.blockCountLong)
                .put("cacheAvailableBlocks", cacheStats.availableBlocksLong)
                .put("cacheFreeBlocks", cacheStats.freeBlocksLong)
                .put("cacheFreeBytes", cacheStats.freeBytes)

            val deviceId = deviceId(context)
            val device = JSONObject()
                .put("deviceId", deviceId)
                .put("appId", context.packageName)
                .put("arch", "armeabi-v7a")
                .put("deviceAbi", "armeabi-v7a")
                .put("supportedAbis", android.os.Build.SUPPORTED_ABIS.joinToString(","))
                .put("manufacturer", android.os.Build.MANUFACTURER ?: "Android")
                .put("model", android.os.Build.MODEL ?: "Android")
                .put("deviceName", android.os.Build.DEVICE ?: "Android")
                .put("productName", android.os.Build.PRODUCT ?: "Android")
                .put("androidRelease", android.os.Build.VERSION.RELEASE ?: "")
                .put("sdkInt", android.os.Build.VERSION.SDK_INT)
                .put("displayLanguage", java.util.Locale.getDefault().language)
                .put("locale", java.util.Locale.getDefault().toLanguageTag())
                .put("isAndroidTv", true)
                .put("hasBrowser", false)
                .put("hasWebView", true)

            val app = JSONObject()
                .put("packageName", context.packageName)
                .put("versionName", pInfo.versionName ?: "1.0.0")
                .put("versionCode", 302131302)
                .put("targetSdkVersion", context.applicationInfo.targetSdkVersion)

            val info = JSONObject()
                .put("schemaVersion", 1)
                .put("paths", paths)
                .put("memory", memory)
                .put("storage", storage)
                .put("device", device)
                .put("app", app)

            output.parentFile?.let { if (!it.exists()) it.mkdirs() }
            FileOutputStream(output).use { fos ->
                OutputStreamWriterCompat.write(fos, info.toString() + "\n")
            }
        } catch (e: Exception) {
            Log.e(TAG, "cannot write android info", e)
        }
    }

    private object OutputStreamWriterCompat {
        fun write(fos: FileOutputStream, text: String) {
            fos.write(text.toByteArray(Charsets.UTF_8))
            fos.flush()
        }
    }

    private fun deviceId(context: Context): String {
        val prefs = context.getSharedPreferences("ace_android_info", Context.MODE_PRIVATE)
        var id = prefs.getString("device_id", null)
        if (id == null) {
            id = UUID.randomUUID().toString()
            prefs.edit().putString("device_id", id).apply()
        }
        return id
    }

    /** Останавливает процесс движка (редко нужно — достаточно остановить сессию). */
    fun shutdown() {
        synchronized(lock) {
            val p = process ?: return
            p.destroy()
            process = null
        }
    }
}

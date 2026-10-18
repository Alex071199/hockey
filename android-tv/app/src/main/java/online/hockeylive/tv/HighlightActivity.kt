package online.hockeylive.tv

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity

/** Веб-просмотрщик обзоров матчей НХЛ (Brightcove embed с nhl.com). */
class HighlightActivity : ComponentActivity() {

    companion object {
        const val EXTRA_URL = "url"
    }

    private var webView: WebView? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val wv = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.setSupportMultipleWindows(false)
            settings.userAgentString =
                "Mozilla/5.0 (Linux; Android 12; SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            webViewClient = WebViewClient()
        }
        setContentView(wv)
        webView = wv

        val url = intent.getStringExtra(EXTRA_URL)
        if (url.isNullOrBlank()) {
            finish()
        } else {
            wv.loadUrl(url)
        }
    }

    override fun onPause() {
        super.onPause()
        webView?.onPause()
    }

    override fun onResume() {
        super.onResume()
        webView?.onResume()
    }

    override fun onDestroy() {
        super.onDestroy()
        webView?.destroy()
        webView = null
    }
}

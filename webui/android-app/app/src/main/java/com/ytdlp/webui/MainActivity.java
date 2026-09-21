package com.ytdlp.webui;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {
    private static final String MINIMAL_SERVER_URL = "http://127.0.0.1:8000";
    private static final String FULL_SERVER_URL = "http://127.0.0.1:8001";
    private static final String MINIMAL_HEALTH_URL = MINIMAL_SERVER_URL + "/api/health";
    private static final String FULL_HEALTH_URL = FULL_SERVER_URL + "/api/health";
    private static final int MAX_RETRIES = 90;

    private WebView webView;
    private ProgressBar progressBar;
    private TextView statusText;
    private LinearLayout loadingLayout;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private int retryCount = 0;
    private volatile String currentServerUrl = MINIMAL_SERVER_URL;
    private volatile boolean webViewLoaded = false;

    private final BroadcastReceiver statusReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String status = intent.getStringExtra("status");
            if ("ready".equals(status)) {
                retryCount = 0;
                String url = intent.getStringExtra("url");
                if (url != null && !url.isEmpty()) {
                    currentServerUrl = url;
                }
                loadWebView(currentServerUrl);
            } else if ("error".equals(status)) {
                String error = intent.getStringExtra("message");
                statusText.setText("启动失败: " + error);
                statusText.setTextColor(Color.parseColor("#ff6b6b"));
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout rootLayout = new LinearLayout(this);
        rootLayout.setOrientation(LinearLayout.VERTICAL);
        rootLayout.setLayoutParams(new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.MATCH_PARENT
        ));

        loadingLayout = new LinearLayout(this);
        loadingLayout.setOrientation(LinearLayout.VERTICAL);
        loadingLayout.setGravity(Gravity.CENTER);
        loadingLayout.setLayoutParams(new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.MATCH_PARENT
        ));
        loadingLayout.setBackgroundColor(Color.parseColor("#1a1a2e"));

        progressBar = new ProgressBar(this);
        progressBar.setLayoutParams(new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ));

        statusText = new TextView(this);
        statusText.setText("正在启动服务...");
        statusText.setTextColor(Color.parseColor("#e0e0e0"));
        statusText.setTextSize(16);
        statusText.setPadding(0, 24, 0, 0);
        statusText.setGravity(Gravity.CENTER);

        loadingLayout.addView(progressBar);
        loadingLayout.addView(statusText);

        webView = new WebView(this);
        webView.setLayoutParams(new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.MATCH_PARENT
        ));
        webView.setVisibility(View.GONE);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setDatabaseEnabled(true);
        settings.setSupportZoom(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                loadingLayout.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
            }
        });
        webView.setWebChromeClient(new WebChromeClient());

        rootLayout.addView(loadingLayout);
        rootLayout.addView(webView);
        setContentView(rootLayout);

        IntentFilter filter = new IntentFilter("com.ytdlp.webui.BACKEND_STATUS");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(statusReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(statusReceiver, filter);
        }

        // Extract bundled ffmpeg binary for fMP4→MP4 conversion
        FFmpegInitializer.ensureBinary(this);

        BackendService.start(this);
        handleShareIntent(getIntent());
        pollServerReady();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleShareIntent(intent);
    }

    private void handleShareIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        String action = intent.getAction();
        if ("android.intent.action.SEND".equals(action)) {
            String text = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (text != null && webView.getVisibility() == View.VISIBLE) {
                String url = extractUrl(text);
                if (url != null) {
                    final String jsUrl = url.replace("'", "\\'");
                    webView.evaluateJavascript(
                        "var inputs = document.querySelectorAll('input');" +
                        "for (var i = 0; i < inputs.length; i++) {" +
                        "  if (inputs[i].placeholder && inputs[i].placeholder.indexOf('URL') >= 0) {" +
                        "    inputs[i].value='" + jsUrl + "';" +
                        "    break;" +
                        "  }" +
                        "}",
                        null
                    );
                }
            }
        }
    }

    private String extractUrl(String text) {
        if (text == null) {
            return null;
        }
        java.util.regex.Pattern pattern = java.util.regex.Pattern.compile("https?://[\\w./?%#&@=+-]+");
        java.util.regex.Matcher matcher = pattern.matcher(text);
        if (matcher.find()) {
            return matcher.group();
        }
        return text.trim();
    }

    private void pollServerReady() {
        new Thread(() -> {
            // First, wait for minimal server (8000) to be ready
            while (retryCount < MAX_RETRIES) {
                if (isHttpReady(MINIMAL_HEALTH_URL)) {
                    break;
                }
                retryCount++;
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    break;
                }
                final int count = retryCount;
                handler.post(() -> statusText.setText(
                    "正在启动服务... (" + count + "s)"
                ));
            }
            
            // Then wait for full server (8001) with additional timeout
            int fullRetryCount = 0;
            int maxFullRetries = 30; // Wait up to 30 seconds for FastAPI
            while (fullRetryCount < maxFullRetries) {
                if (isHttpReady(FULL_HEALTH_URL)) {
                    currentServerUrl = FULL_SERVER_URL;
                    handler.post(() -> loadWebView(currentServerUrl));
                    return;
                }
                fullRetryCount++;
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    break;
                }
                final int count = fullRetryCount;
                handler.post(() -> statusText.setText(
                    "正在启动完整服务... (" + count + "s)"
                ));
            }
            
            // Fallback to minimal server if full server not available
            if (isHttpReady(MINIMAL_HEALTH_URL)) {
                currentServerUrl = MINIMAL_SERVER_URL;
                handler.post(() -> {
                    statusText.setText("使用基础模式 (部分功能不可用)");
                    loadWebView(currentServerUrl);
                });
                return;
            }
            
            handler.post(() -> {
                statusText.setText("服务启动超时，请重启应用");
                statusText.setTextColor(Color.parseColor("#ff6b6b"));
            });
        }).start();
    }

    private String chooseHealthyUrl() {
        if (isHttpReady(FULL_HEALTH_URL)) {
            return FULL_SERVER_URL;
        }
        if (isHttpReady(MINIMAL_HEALTH_URL)) {
            return MINIMAL_SERVER_URL;
        }
        return null;
    }

    private boolean isHttpReady(String urlString) {
        java.net.HttpURLConnection conn = null;
        try {
            java.net.URL url = new java.net.URL(urlString);
            conn = (java.net.HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(1500);
            conn.setReadTimeout(1500);
            conn.setRequestMethod("GET");
            return conn.getResponseCode() == 200;
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private void loadWebView(String serverUrl) {
        String currentUrl = webView.getUrl();
        if (webViewLoaded && serverUrl.equals(currentUrl)) {
            return;
        }
        webViewLoaded = true;
        webView.loadUrl(serverUrl);
    }

    @Override
    protected void onDestroy() {
        try {
            unregisterReceiver(statusReceiver);
        } catch (Exception e) {
            // Receiver not registered.
        }
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}

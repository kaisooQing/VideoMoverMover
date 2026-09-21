package com.ytdlp.webui;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.net.HttpURLConnection;
import java.net.URL;

public class BackendService extends Service {
    private static final String TAG = "VideoMover-Backend";
    private static final String CHANNEL_ID = "videomover_backend";
    private static final String MINIMAL_SERVER_URL = "http://127.0.0.1:8000";
    private static final String FULL_SERVER_URL = "http://127.0.0.1:8001";
    private static final String MINIMAL_HEALTH_URL = MINIMAL_SERVER_URL + "/api/health";
    private static final String FULL_HEALTH_URL = FULL_SERVER_URL + "/api/health";

    private Thread serverThread;
    private volatile boolean running = false;
    private volatile String serverError = null;

    public static void start(Context context) {
        Intent intent = new Intent(context, BackendService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }

    public static void stop(Context context) {
        Intent intent = new Intent(context, BackendService.class);
        context.stopService(intent);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("视频搬运工")
            .setContentText("正在启动服务...")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build();

        startForeground(1, notification);

        if (!running) {
            running = true;
            startPythonServer();
        }

        return START_STICKY;
    }

    private void startPythonServer() {
        serverThread = new Thread(() -> {
            try {
                ensurePythonStarted();
                Log.i(TAG, "Initializing Python...");
                Python py = Python.getInstance();
                Log.i(TAG, "Python initialized, starting server...");
                py.getModule("start_server").callAttr("start", getApplicationContext());
                Log.i(TAG, "Python backend start called");

                boolean minimalReady = false;
                for (int i = 0; i < 90; i++) {
                    Thread.sleep(1000);

                    Object error = py.getModule("start_server").callAttr("get_startup_error");
                    if (error != null && !"None".equals(error.toString())) {
                        serverError = error.toString();
                        Log.e(TAG, "Server startup error: " + serverError);
                        broadcastError(serverError);
                        updateNotification("服务启动失败");
                        return;
                    }

                    if (!minimalReady) {
                        Object ready = py.getModule("start_server").callAttr("is_server_ready");
                        if (ready != null && "True".equals(ready.toString()) && isHttpReady(MINIMAL_HEALTH_URL)) {
                            minimalReady = true;
                            Log.i(TAG, "Minimal bootstrap server is ready");
                            broadcastReady(MINIMAL_SERVER_URL);
                            updateNotification("引导服务已就绪");
                        }
                    }

                    if (minimalReady) {
                        Object ready = py.getModule("start_server").callAttr("is_full_server_ready");
                        if (ready != null && "True".equals(ready.toString()) && isHttpReady(FULL_HEALTH_URL)) {
                            Log.i(TAG, "Full FastAPI server is ready");
                            broadcastReady(FULL_SERVER_URL);
                            updateNotification("完整服务已运行");
                            return;
                        }
                    }

                    Log.i(TAG, "Waiting for server... (" + (i + 1) + "s)");
                }

                if (minimalReady) {
                    Log.w(TAG, "Full server did not come up in time; keeping minimal server");
                    updateNotification("引导服务运行中");
                } else {
                    serverError = "Backend did not open port 8000 within 90 seconds";
                    Log.e(TAG, serverError);
                    broadcastError(serverError);
                    updateNotification("服务启动超时");
                }
            } catch (Exception e) {
                String msg = e.getClass().getSimpleName() + ": " + e.getMessage();
                Log.e(TAG, "Failed to start Python backend", e);
                serverError = msg;
                broadcastError(msg);
                updateNotification("服务启动失败: " + msg);
            }
        });
        serverThread.setDaemon(true);
        serverThread.start();
    }

    private void ensurePythonStarted() {
        if (!Python.isStarted()) {
            Log.i(TAG, "Starting Chaquopy runtime");
            Python.start(new AndroidPlatform(getApplicationContext()));
        }
    }

    private boolean isHttpReady(String urlString) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlString);
            conn = (HttpURLConnection) url.openConnection();
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

    private void broadcastReady(String url) {
        Intent intent = new Intent("com.ytdlp.webui.BACKEND_STATUS");
        intent.putExtra("status", "ready");
        intent.putExtra("url", url);
        sendBroadcast(intent);
    }

    private void broadcastError(String message) {
        Intent intent = new Intent("com.ytdlp.webui.BACKEND_STATUS");
        intent.putExtra("status", "error");
        intent.putExtra("message", message);
        sendBroadcast(intent);
    }

    private void updateNotification(String text) {
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("视频搬运工")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setOngoing(true)
                .build();
            manager.notify(1, notification);
        }
    }

    @Override
    public void onDestroy() {
        running = false;
        try {
            if (Python.isStarted()) {
                Python py = Python.getInstance();
                py.getModule("start_server").callAttr("stop");
            }
        } catch (Exception e) {
            Log.w(TAG, "Error stopping server", e);
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "视频搬运工",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("视频搬运工 后台服务");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }
}

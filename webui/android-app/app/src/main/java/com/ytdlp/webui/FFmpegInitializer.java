package com.ytdlp.webui;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Extracts the bundled ffmpeg binary from assets to internal storage
 * and makes it executable.
 *
 * The binary is a static build for Android arm64-v8a (FFmpeg 9.0, LGPL).
 * It's used to convert fMP4/TS to standard MP4 for mobile playback.
 */
public class FFmpegInitializer {

    private static final String TAG = "FFmpegInitializer";
    private static final String ASSET_NAME = "ffmpeg";
    private static final String BINARY_NAME = "ffmpeg";

    /**
     * Extract ffmpeg from assets to internal storage if not already present.
     * Makes it executable. Safe to call multiple times.
     *
     * @return Path to the ffmpeg binary, or null if extraction failed
     */
    public static String ensureBinary(Context context) {
        File binary = new File(context.getFilesDir(), BINARY_NAME);

        // Check if already extracted (skip if exists and non-trivial size)
        if (binary.exists() && binary.length() > 1024 * 1024) {
            return binary.getAbsolutePath();
        }

        // Extract from assets
        try (InputStream is = context.getAssets().open(ASSET_NAME);
             FileOutputStream fos = new FileOutputStream(binary)) {

            byte[] buffer = new byte[1024 * 64];
            int bytesRead;
            while ((bytesRead = is.read(buffer)) != -1) {
                fos.write(buffer, 0, bytesRead);
            }
            fos.flush();

            // Make executable
            if (!binary.setExecutable(true)) {
                // Fallback: use chmod
                try {
                    Process chmod = Runtime.getRuntime().exec(
                        new String[]{"chmod", "755", binary.getAbsolutePath()});
                    chmod.waitFor();
                } catch (Exception e) {
                    Log.w(TAG, "chmod failed: " + e.getMessage());
                }
            }

            Log.i(TAG, "ffmpeg extracted to: " + binary.getAbsolutePath() +
                  " (" + binary.length() + " bytes)");
            return binary.getAbsolutePath();

        } catch (IOException e) {
            Log.e(TAG, "Failed to extract ffmpeg", e);
            return null;
        } catch (Exception e) {
            Log.e(TAG, "Unexpected error extracting ffmpeg", e);
            return null;
        }
    }
}

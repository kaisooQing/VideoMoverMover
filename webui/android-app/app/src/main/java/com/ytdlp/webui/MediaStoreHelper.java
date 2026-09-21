package com.ytdlp.webui;

import android.content.ContentValues;
import android.content.Context;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;

public class MediaStoreHelper {

    private static final String TAG = "MediaStoreHelper";

    /**
     * Copy a file to public MediaStore so it appears in gallery.
     * Videos go to DCIM/Camera, images go to DCIM/Camera.
     * Returns the public path on success, or null on failure.
     */
    public static String copyToGallery(Context context, String sourcePath) {
        File sourceFile = new File(sourcePath);
        if (!sourceFile.exists()) {
            Log.w(TAG, "Source file not found: " + sourcePath);
            return null;
        }

        String fileName = sourceFile.getName();
        String mimeType = getMimeType(fileName);
        boolean isVideo = mimeType.startsWith("video/");

        // Try MediaStore approach (Android 10+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            String result = copyViaMediaStore(context, sourceFile, fileName, mimeType, isVideo);
            if (result != null) return result;
        }

        // Fallback: direct file copy for older Android or if MediaStore fails
        return copyDirect(context, sourceFile, fileName, mimeType, isVideo);
    }

    private static String copyViaMediaStore(Context context, File sourceFile,
            String fileName, String mimeType, boolean isVideo) {
        try {
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            values.put(MediaStore.MediaColumns.MIME_TYPE, mimeType);

            // Use DCIM/Camera — the standard directory all gallery apps scan
            values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                    Environment.DIRECTORY_DCIM + "/Camera");

            values.put(MediaStore.MediaColumns.IS_PENDING, 1);

            Uri collection;
            if (isVideo) {
                collection = MediaStore.Video.Media.EXTERNAL_CONTENT_URI;
            } else if (mimeType.startsWith("audio/")) {
                collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
            } else {
                collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
            }

            Uri uri = context.getContentResolver().insert(collection, values);
            if (uri == null) {
                Log.w(TAG, "MediaStore insert failed for: " + fileName);
                return null;
            }

            OutputStream out = context.getContentResolver().openOutputStream(uri);
            if (out == null) {
                Log.w(TAG, "MediaStore openOutputStream failed for: " + fileName);
                return null;
            }

            copyStream(new FileInputStream(sourceFile), out);

            // Clear IS_PENDING so gallery can see it
            values.clear();
            values.put(MediaStore.MediaColumns.IS_PENDING, 0);
            context.getContentResolver().update(uri, values, null, null);

            String publicPath = Environment.getExternalStorageDirectory().getAbsolutePath()
                    + "/DCIM/Camera/" + fileName;

            Log.i(TAG, "Copied to gallery via MediaStore: " + publicPath);
            return publicPath;

        } catch (Exception e) {
            Log.e(TAG, "copyViaMediaStore failed", e);
            return null;
        }
    }

    private static String copyDirect(Context context, File sourceFile,
            String fileName, String mimeType, boolean isVideo) {
        try {
            File dcim = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM);
            File cameraDir = new File(dcim, "Camera");
            if (!cameraDir.exists()) {
                cameraDir.mkdirs();
            }

            File destFile = new File(cameraDir, fileName);
            // Avoid overwrite
            if (destFile.exists()) {
                String base = fileName.contains(".")
                    ? fileName.substring(0, fileName.lastIndexOf('.'))
                    : fileName;
                String ext = fileName.contains(".")
                    ? fileName.substring(fileName.lastIndexOf('.'))
                    : "";
                destFile = new File(cameraDir, base + "_" + System.currentTimeMillis() + ext);
            }

            java.io.InputStream in = new FileInputStream(sourceFile);
            java.io.OutputStream out = new java.io.FileOutputStream(destFile);
            copyStream(in, out);

            // Notify MediaScanner so gallery picks it up
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                try {
                    android.content.Intent scanIntent = new android.content.Intent(
                            android.content.Intent.ACTION_MEDIA_SCANNER_SCAN_FILE);
                    scanIntent.setData(Uri.fromFile(destFile));
                    context.sendBroadcast(scanIntent);
                } catch (Exception e) {
                    Log.w(TAG, "MediaScanner broadcast failed", e);
                }
            }

            Log.i(TAG, "Copied to gallery directly: " + destFile.getAbsolutePath());
            return destFile.getAbsolutePath();

        } catch (Exception e) {
            Log.e(TAG, "copyDirect failed", e);
            return null;
        }
    }

    private static void copyStream(java.io.InputStream in, java.io.OutputStream out) throws java.io.IOException {
        byte[] buffer = new byte[8192];
        int len;
        while ((len = in.read(buffer)) != -1) {
            out.write(buffer, 0, len);
        }
        in.close();
        out.close();
    }

    /**
     * Trigger MediaScanner to scan a file so it appears in gallery immediately.
     * Works for any directory (DCIM, Download, etc.).
     */
    public static void scanFile(Context context, String path) {
        if (path == null || path.isEmpty()) {
            return;
        }
        try {
            File file = new File(path);
            if (!file.exists()) {
                Log.w(TAG, "scanFile: file not found: " + path);
                return;
            }
            MediaScannerConnection.scanFile(context, new String[]{path}, null, null);
            Log.i(TAG, "scanFile triggered: " + path);
        } catch (Exception e) {
            Log.e(TAG, "scanFile failed", e);
        }
    }

    private static String getMimeType(String fileName) {
        String lower = fileName.toLowerCase();
        if (lower.endsWith(".mp4") || lower.endsWith(".mkv") || lower.endsWith(".webm") || lower.endsWith(".flv")) return "video/mp4";
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
        if (lower.endsWith(".png")) return "image/png";
        if (lower.endsWith(".gif")) return "image/gif";
        if (lower.endsWith(".mp3")) return "audio/mpeg";
        if (lower.endsWith(".webp")) return "image/webp";
        return "application/octet-stream";
    }
}

package com.ytdlp.webui;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.util.Log;

import java.io.File;
import java.nio.ByteBuffer;

/**
 * MediaMuxerHelper — remux/merge media files into MP4 using Android's
 * MediaMuxer. No FFmpeg required.
 */
public class MediaMuxerHelper {

    private static final String TAG = "MediaMuxerHelper";
    private static final int BUFFER_SIZE = 2 * 1024 * 1024; // 2 MB buffer

    /**
     * Merge video and audio into a single MP4 file.
     *
     * @param videoPath  Path to the video .m4s file
     * @param audioPath  Path to the audio .m4s file
     * @param outputPath Path for the output .mp4 file
     * @return true on success, false on failure
     */
    public static boolean merge(String videoPath, String audioPath, String outputPath) {
        MediaExtractor videoExtractor = null;
        MediaExtractor audioExtractor = null;
        MediaMuxer muxer = null;

        try {
            File videoFile = new File(videoPath);
            File audioFile = new File(audioPath);
            if (!videoFile.exists() || !audioFile.exists()) {
                Log.e(TAG, "Input file missing: video=" + videoFile.exists() + " audio=" + audioFile.exists());
                return false;
            }

            // Create muxer (output to MP4)
            muxer = new MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);

            // --- Add video track ---
            videoExtractor = new MediaExtractor();
            videoExtractor.setDataSource(videoPath);

            MediaFormat videoFormat = null;
            int videoTrackIndex = -1;

            for (int i = 0; i < videoExtractor.getTrackCount(); i++) {
                MediaFormat fmt = videoExtractor.getTrackFormat(i);
                String mime = fmt.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("video/")) {
                    videoFormat = fmt;
                    videoTrackIndex = muxer.addTrack(videoFormat);
                    break;
                }
            }

            if (videoTrackIndex < 0) {
                Log.e(TAG, "No video track found in: " + videoPath);
                return false;
            }

            // --- Add audio track ---
            audioExtractor = new MediaExtractor();
            audioExtractor.setDataSource(audioPath);

            MediaFormat audioFormat = null;
            int audioTrackIndex = -1;

            for (int i = 0; i < audioExtractor.getTrackCount(); i++) {
                MediaFormat fmt = audioExtractor.getTrackFormat(i);
                String mime = fmt.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    audioFormat = fmt;
                    audioTrackIndex = muxer.addTrack(audioFormat);
                    break;
                }
            }

            if (audioTrackIndex < 0) {
                Log.e(TAG, "No audio track found in: " + audioPath);
                return false;
            }

            // --- Start muxing ---
            muxer.start();

            ByteBuffer buffer = ByteBuffer.allocateDirect(BUFFER_SIZE);
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();

            // Write video samples
            videoExtractor.selectTrack(0);
            while (true) {
                int sampleSize = videoExtractor.readSampleData(buffer, 0);
                if (sampleSize < 0) break;

                bufferInfo.offset = 0;
                bufferInfo.size = sampleSize;
                bufferInfo.presentationTimeUs = videoExtractor.getSampleTime();
                bufferInfo.flags = videoExtractor.getSampleFlags();

                muxer.writeSampleData(videoTrackIndex, buffer, bufferInfo);
                videoExtractor.advance();
            }

            // Write audio samples
            audioExtractor.selectTrack(0);
            while (true) {
                int sampleSize = audioExtractor.readSampleData(buffer, 0);
                if (sampleSize < 0) break;

                bufferInfo.offset = 0;
                bufferInfo.size = sampleSize;
                bufferInfo.presentationTimeUs = audioExtractor.getSampleTime();
                bufferInfo.flags = audioExtractor.getSampleFlags();

                muxer.writeSampleData(audioTrackIndex, buffer, bufferInfo);
                audioExtractor.advance();
            }

            muxer.stop();
            Log.i(TAG, "Merge success: " + outputPath);
            return true;

        } catch (Exception e) {
            Log.e(TAG, "Merge failed", e);
            return false;
        } finally {
            try { if (muxer != null) muxer.release(); } catch (Exception ignored) {}
            try { if (videoExtractor != null) videoExtractor.release(); } catch (Exception ignored) {}
            try { if (audioExtractor != null) audioExtractor.release(); } catch (Exception ignored) {}
        }
    }

    /**
     * Remux a single media file (fragmented MP4, TS, etc.) into a standard
     * MP4 with correct duration metadata and seeking support.
     *
     * Key improvements over previous version:
     * - Ensures first sample is marked as key frame (fixes "unable to play")
     * - Larger buffer (2MB) for high-bitrate samples
     * - Detailed logging for debugging
     * - Verifies track count before muxing
     *
     * @param inputPath  Path to input file (fMP4, TS, etc.)
     * @param outputPath Path for output .mp4 file
     * @return true on success, false on failure
     */
    public static boolean remux(String inputPath, String outputPath) {
        MediaExtractor videoExtractor = null;
        MediaExtractor audioExtractor = null;
        MediaMuxer muxer = null;

        try {
            File inputFile = new File(inputPath);
            if (!inputFile.exists()) {
                Log.e(TAG, "Remux input not found: " + inputPath);
                return false;
            }

            long inputSize = inputFile.length();
            Log.i(TAG, "Remux start: " + inputPath + " (" + inputSize + " bytes)");

            videoExtractor = new MediaExtractor();
            videoExtractor.setDataSource(inputPath);

            int trackCount = videoExtractor.getTrackCount();
            Log.i(TAG, "Remux: found " + trackCount + " tracks");

            if (trackCount == 0) {
                Log.e(TAG, "Remux: no tracks found in file");
                return false;
            }

            muxer = new MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);

            // Video track
            int muxerVideoTrack = -1;
            int videoTrack = -1;
            MediaFormat videoFormat = null;
            for (int i = 0; i < trackCount; i++) {
                MediaFormat fmt = videoExtractor.getTrackFormat(i);
                String mime = fmt.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("video/")) {
                    videoExtractor.selectTrack(i);
                    muxerVideoTrack = muxer.addTrack(fmt);
                    videoTrack = i;
                    videoFormat = fmt;
                    Log.i(TAG, "Remux: video track " + i + " mime=" + mime +
                          " " + fmt.getInteger(MediaFormat.KEY_WIDTH) + "x" +
                          fmt.getInteger(MediaFormat.KEY_HEIGHT));
                    break;
                }
            }

            // Audio track (separate extractor on same file)
            audioExtractor = new MediaExtractor();
            audioExtractor.setDataSource(inputPath);
            int muxerAudioTrack = -1;
            int audioTrack = -1;
            for (int i = 0; i < audioExtractor.getTrackCount(); i++) {
                MediaFormat fmt = audioExtractor.getTrackFormat(i);
                String mime = fmt.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    audioExtractor.selectTrack(i);
                    muxerAudioTrack = muxer.addTrack(fmt);
                    audioTrack = i;
                    Log.i(TAG, "Remux: audio track " + i + " mime=" + mime);
                    break;
                }
            }

            if (muxerVideoTrack < 0 && muxerAudioTrack < 0) {
                Log.e(TAG, "Remux: no video or audio track found");
                return false;
            }

            muxer.start();

            ByteBuffer buffer = ByteBuffer.allocateDirect(BUFFER_SIZE);
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();

            int videoSampleCount = 0;
            int videoKeyFrameCount = 0;
            long firstVideoPts = Long.MAX_VALUE;
            long lastVideoPts = 0;
            boolean firstVideoSample = true;

            // Write video samples
            if (muxerVideoTrack >= 0) {
                Log.i(TAG, "Remux: writing video samples...");
                while (true) {
                    int sampleSize = videoExtractor.readSampleData(buffer, 0);
                    if (sampleSize < 0) break;

                    bufferInfo.offset = 0;
                    bufferInfo.size = sampleSize;
                    bufferInfo.presentationTimeUs = videoExtractor.getSampleTime();
                    bufferInfo.flags = videoExtractor.getSampleFlags();

                    // Ensure the first sample is marked as a key frame.
                    // Some fMP4 files don't set sample_depends_on properly,
                    // causing MediaExtractor to not report sync samples.
                    // Without at least one key frame, the output is unplayable.
                    if (firstVideoSample) {
                        bufferInfo.flags |= MediaCodec.BUFFER_FLAG_KEY_FRAME;
                        firstVideoSample = false;
                    }

                    if ((bufferInfo.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0) {
                        videoKeyFrameCount++;
                    }

                    if (bufferInfo.presentationTimeUs < firstVideoPts) {
                        firstVideoPts = bufferInfo.presentationTimeUs;
                    }
                    lastVideoPts = bufferInfo.presentationTimeUs;

                    muxer.writeSampleData(muxerVideoTrack, buffer, bufferInfo);
                    videoSampleCount++;
                    videoExtractor.advance();
                }
                Log.i(TAG, "Remux: video done, " + videoSampleCount + " samples, " +
                      videoKeyFrameCount + " key frames, " +
                      "PTS " + firstVideoPts + "-" + lastVideoPts);
            }

            int audioSampleCount = 0;
            long firstAudioPts = Long.MAX_VALUE;
            long lastAudioPts = 0;

            // Write audio samples
            if (muxerAudioTrack >= 0) {
                Log.i(TAG, "Remux: writing audio samples...");
                while (true) {
                    int sampleSize = audioExtractor.readSampleData(buffer, 0);
                    if (sampleSize < 0) break;

                    bufferInfo.offset = 0;
                    bufferInfo.size = sampleSize;
                    bufferInfo.presentationTimeUs = audioExtractor.getSampleTime();
                    bufferInfo.flags = audioExtractor.getSampleFlags();

                    if (bufferInfo.presentationTimeUs < firstAudioPts) {
                        firstAudioPts = bufferInfo.presentationTimeUs;
                    }
                    lastAudioPts = bufferInfo.presentationTimeUs;

                    muxer.writeSampleData(muxerAudioTrack, buffer, bufferInfo);
                    audioSampleCount++;
                    audioExtractor.advance();
                }
                Log.i(TAG, "Remux: audio done, " + audioSampleCount + " samples, " +
                      "PTS " + firstAudioPts + "-" + lastAudioPts);
            }

            if (videoSampleCount == 0 && audioSampleCount == 0) {
                Log.e(TAG, "Remux: no samples written, aborting");
                muxer.stop();
                return false;
            }

            muxer.stop();

            // Verify output file
            File outFile = new File(outputPath);
            long outputSize = outFile.length();
            Log.i(TAG, "Remux success: " + outputPath + " (" + outputSize + " bytes)" +
                  " video=" + videoSampleCount + " audio=" + audioSampleCount);

            // Sanity check: output should be at least 50% of input size
            if (outputSize < inputSize / 2) {
                Log.w(TAG, "Remux warning: output much smaller than input (" +
                      outputSize + " vs " + inputSize + ")");
            }

            return true;

        } catch (Exception e) {
            Log.e(TAG, "Remux failed", e);
            return false;
        } finally {
            try { if (muxer != null) muxer.release(); } catch (Exception ignored) {}
            try { if (videoExtractor != null) videoExtractor.release(); } catch (Exception ignored) {}
            try { if (audioExtractor != null) audioExtractor.release(); } catch (Exception ignored) {}
        }
    }
}

package com.mthread;

import android.graphics.Bitmap;
import android.util.Base64;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * Screen capture that scales and compresses on the phone, so the cable carries
 * a thumbnail instead of a framebuffer.
 *
 * <p>Why this exists, in numbers measured on a Pixel 8 Pro at 1344x2992:
 *
 * <ul>
 *   <li>{@code adb exec-out screencap -p} - 2.1 s per frame. The device spends
 *       almost all of it PNG-encoding sixteen megabytes.</li>
 *   <li>{@code adb exec-out screencap} - 2.9 s per frame. No encoding, but now
 *       all sixteen megabytes cross the USB link, at about 5 MB/s.</li>
 *   <li>This, at 480 pixels wide and quality 60 - the raw capture costs about
 *       300 ms on the device, the scale and JPEG maybe 30, and the cable
 *       carries some 40 kB.</li>
 * </ul>
 *
 * <p>So the ceiling is the capture itself, which is roughly three frames a
 * second. That is not video and this is not scrcpy: scrcpy is fast because it
 * feeds the display straight into the hardware H.264 encoder, which needs a
 * decoder on the other end. Three frames a second is enough to see what is on
 * the phone and where a drawing is going to land, which is what this is for.
 *
 * <p>Pull-based: one line in, one frame out, so the host sets the rate and
 * frames never queue up behind a slow reader.
 *
 * <pre>
 *   &lt;maxWidth&gt; &lt;quality&gt;   capture, reply with "F " and the JPEG in base64
 *   Q                          quit
 * </pre>
 *
 * <p>Base64, for a picture, over a link that ought to be binary-safe. In
 * practice it is not: adb on Windows still turns a line feed into a carriage
 * return and a line feed on the way out, and a JPEG is full of line feeds - so
 * the image arrives longer than it left, the declared length no longer matches,
 * and every frame after the first is out of step by however many newlines the
 * one before it happened to contain. Base64 has no byte the translation can
 * touch. It costs a third more on a 25 kB frame and removes the whole class of
 * problem.
 */
public final class Mirror {

    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));

        System.out.println("READY");
        System.out.flush();

        String line;
        while ((line = in.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) {
                continue;
            }
            if (line.startsWith("Q")) {
                break;
            }

            String[] parts = line.split("\\s+");
            int maxWidth = parts.length > 0 ? Integer.parseInt(parts[0]) : 480;
            int quality = parts.length > 1 ? Integer.parseInt(parts[1]) : 60;

            try {
                byte[] jpeg = capture(maxWidth, quality);
                System.out.println("F " + Base64.encodeToString(jpeg, Base64.NO_WRAP));
            } catch (Throwable error) {
                System.out.println("E " + error);
            }
            System.out.flush();
        }
    }

    /** Capture the screen, scaled to *maxWidth* on its longer edge, as JPEG. */
    private static byte[] capture(int maxWidth, int quality) throws Exception {
        byte[] raw = readAll(Runtime.getRuntime().exec("screencap").getInputStream());
        if (raw.length < 16) {
            throw new IllegalStateException("screencap returned " + raw.length + " bytes");
        }

        ByteBuffer header = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN);
        int width = header.getInt();
        int height = header.getInt();
        header.getInt();  // pixel format; always RGBA_8888 in practice

        // Android 10 added a colour space to the header, so its size is not a
        // constant. The pixels are the last width*height*4 bytes either way.
        int offset = raw.length - width * height * 4;
        if (offset < 12) {
            throw new IllegalStateException(
                    "screencap gave " + raw.length + " bytes for " + width + "x" + height);
        }

        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        // ARGB_8888 is stored RGBA in memory on a little-endian machine, which
        // is exactly what screencap produces, so the buffer copies straight in.
        ByteBuffer pixels = ByteBuffer.wrap(raw, offset, width * height * 4);
        bitmap.copyPixelsFromBuffer(pixels);

        int longer = Math.max(width, height);
        if (longer > maxWidth) {
            float scale = (float) maxWidth / longer;
            bitmap = Bitmap.createScaledBitmap(
                    bitmap, Math.round(width * scale), Math.round(height * scale), true);
        }

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, buffer);
        return buffer.toByteArray();
    }

    private static byte[] readAll(InputStream stream) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream(1 << 22);
        byte[] chunk = new byte[1 << 16];
        int read;
        while ((read = stream.read(chunk)) > 0) {
            buffer.write(chunk, 0, read);
        }
        return buffer.toByteArray();
    }

    private Mirror() {
    }
}

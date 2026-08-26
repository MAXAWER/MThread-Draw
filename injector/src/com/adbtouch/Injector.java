package com.adbtouch;

import android.os.SystemClock;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.MotionEvent;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Method;

/**
 * A touch injector that stays alive, so a stroke costs one process instead of
 * one process per point.
 *
 * <p>The problem it solves: on a recent Android the shell user cannot write to
 * /dev/input - SELinux denies the shell domain, whatever the file mode says -
 * so drawing has to go through the framework. The `input` command does that,
 * but every invocation starts a new process, which measures at about 110 ms on
 * a Pixel 8 Pro. A stroke of sixty points then takes seven seconds, and no
 * amount of pacing makes a seven-second stroke look like a hand.
 *
 * <p>This is the same trick scrcpy uses: a tiny jar run once through
 * app_process under the shell uid, which reads points from stdin and injects
 * them itself. Hidden-API restrictions apply to applications, not to a process
 * started this way, so InputManager can be reached by reflection. Injection
 * then costs microseconds, and the timing between points becomes ours to
 * choose - which is the whole point, because the timing is what a hand is.
 *
 * <p>The protocol is one command per line, chosen to be trivial to generate:
 *
 * <pre>
 *   D &lt;x&gt; &lt;y&gt;   press down and start a stroke
 *   M &lt;x&gt; &lt;y&gt;   move
 *   U &lt;x&gt; &lt;y&gt;   lift
 *   S &lt;ms&gt;      wait, in milliseconds; fractions allowed
 *   P           ping - replies OK, so the caller can wait for a batch to land
 *   Q           quit
 * </pre>
 */
public final class Injector {

    /** InputManager.INJECT_INPUT_EVENT_MODE_ASYNC: do not wait for the app. */
    private static final int INJECT_ASYNC = 0;

    private static Object manager;
    private static Method inject;

    /** Events sharing a millisecond get coalesced, so time is forced forward. */
    private static long lastEventTime;

    private static void connect() throws Exception {
        // Android 14 moved getInstance to InputManagerGlobal and left the old
        // entry point behind. Try the new home first, then the old one.
        try {
            Class<?> global = Class.forName("android.hardware.input.InputManagerGlobal");
            manager = global.getMethod("getInstance").invoke(null);
            inject = global.getMethod("injectInputEvent", InputEvent.class, int.class);
            return;
        } catch (Throwable ignored) {
            // Fall through to the pre-14 API.
        }
        Class<?> legacy = Class.forName("android.hardware.input.InputManager");
        manager = legacy.getMethod("getInstance").invoke(null);
        inject = legacy.getMethod("injectInputEvent", InputEvent.class, int.class);
    }

    private static void send(int action, float x, float y, long downTime) throws Exception {
        long now = Math.max(SystemClock.uptimeMillis(), lastEventTime + 1);
        lastEventTime = now;
        MotionEvent event = MotionEvent.obtain(
                downTime, now, action, x, y,
                1.0f,   // pressure
                1.0f,   // size
                0,      // metaState
                1.0f,   // xPrecision
                1.0f,   // yPrecision
                0,      // deviceId
                0);     // edgeFlags
        event.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        try {
            inject.invoke(manager, event, INJECT_ASYNC);
        } finally {
            event.recycle();
        }
    }

    private static void pause(double millis) throws InterruptedException {
        if (millis <= 0) {
            return;
        }
        // Thread.sleep is only good to a millisecond or so, which is finer than
        // a touchscreen samples anyway; the fractional part is carried by the
        // nanosecond argument rather than rounded away.
        long whole = (long) millis;
        int nanos = (int) ((millis - whole) * 1_000_000);
        Thread.sleep(whole, nanos);
    }

    public static void main(String[] args) {
        try {
            connect();
        } catch (Throwable error) {
            System.out.println("ERR cannot reach InputManager: " + error);
            System.out.flush();
            return;
        }

        System.out.println("READY");
        System.out.flush();

        long downTime = 0;
        try (BufferedReader in = new BufferedReader(new InputStreamReader(System.in))) {
            String line;
            while ((line = in.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) {
                    continue;
                }
                char command = line.charAt(0);
                String[] parts = line.split("\\s+");

                try {
                    switch (command) {
                        case 'D':
                            downTime = Math.max(SystemClock.uptimeMillis(), lastEventTime + 1);
                            send(MotionEvent.ACTION_DOWN,
                                    Float.parseFloat(parts[1]), Float.parseFloat(parts[2]), downTime);
                            break;
                        case 'M':
                            send(MotionEvent.ACTION_MOVE,
                                    Float.parseFloat(parts[1]), Float.parseFloat(parts[2]), downTime);
                            break;
                        case 'U':
                            send(MotionEvent.ACTION_UP,
                                    Float.parseFloat(parts[1]), Float.parseFloat(parts[2]), downTime);
                            break;
                        case 'S':
                            pause(Double.parseDouble(parts[1]));
                            break;
                        case 'P':
                            System.out.println("OK");
                            System.out.flush();
                            break;
                        case 'Q':
                            return;
                        default:
                            System.out.println("ERR unknown command: " + line);
                            System.out.flush();
                            break;
                    }
                } catch (Throwable error) {
                    System.out.println("ERR " + line + ": " + error);
                    System.out.flush();
                }
            }
        } catch (Throwable error) {
            System.out.println("ERR " + error);
            System.out.flush();
        }
    }

    private Injector() {
    }
}

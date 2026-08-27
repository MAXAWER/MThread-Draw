# Changelog

## 1.3.0

The release where both windows became native and the installer started
saying something.

- **The Windows window is WinUI 3, and it is the one that gets installed.**
  Until now the installer carried the Tk window, so installing MThread Draw on
  Windows got the old interface, slowly, and the native one was only in a zip
  nobody had a reason to open. The Tk window is gone: `mthread_draw/app.py`,
  the `gui` extra and the customtkinter dependency with it. Linux keeps the
  command line and the library.
- **A macOS window, in SwiftUI.** Frosted glass over `NSVisualEffectView` with
  behind-window blending, the same phone view with drag placement and the same
  eraser, driving the same engine over a pipe. `tools/build_macos.py`
  assembles the bundle around `swift build` and makes the disk image.
- **The installer has a user interface.** Without one an MSI shows "gathering
  required information", installs, and closes without a word, so a successful
  install cannot be told apart from a failed one - and it was read as failure.
  Now: welcome, where to put it, progress, finished, and a ticked offer to
  start the program. Apps & features shows the install folder, and a new
  version replaces the old one instead of sitting beside it.
- **Builds happen outside the checkout.** This tree lives in OneDrive on one
  machine, and a sync client holds handles on files while it uploads them.
  Writing several thousand of them into a synced folder failed at a different
  step every time, always with an access denied that named a file rather than
  the cause. Everything is staged in temp; only the finished installer and zip
  are copied into `dist/`.

## 1.2.0

The release that made the window an editor rather than a loader.

- **Layers.** Several pictures can be loaded and arranged against each other
  before anything is drawn, each with its own placement and its own tracer
  settings. Hide one, reorder them, remove one; what is drawn is every visible
  layer in order.
- **An eraser.** Drag across the live view with the eraser on and the strokes
  under the cursor come out. Which strokes are near enough is decided after
  placement, because the cursor is over a picture of the phone rather than over
  the tracer's coordinate space. Re-tracing forgets erasures rather than
  misapplying them: stroke five of one tracing is not stroke five of the next.
- **Flip, and buttons for the transforms that are not gestures.** `Flip`,
  `Fit` and `Undo erase` sit under the phone; `Placement.mirrored` flips rather
  than sets, so flipping twice is not flipping.
- **A screenshot taken by hand can stand in for capture.** When ADB capture
  fails there is otherwise nothing to place a drawing against. A still picture
  does not update, but its proportions are the ones that matter, and placement
  now works with no phone attached at all - so a drawing can be arranged before
  the cable is anywhere near.
- **Shapes and text from the command line**, with nothing to prepare:
  `mthread shape heart`, `mthread shape star --points 7 --rotate 20`,
  `mthread text "hello" --font arial.ttf`. Seven shapes, and text in any font
  the machine has.

- **Place the drawing by hand.** Drag it over the live view, wheel to resize,
  Shift and wheel to turn, double-click to fit again. `Placement` holds the
  position in fractions of the screen and degrees, so it survives the phone
  being turned; a scale of one means "as large as it goes with a margin",
  whatever the drawing and whatever the phone.
- **Recordings that replay on a different phone.** `mthread.gestures` decodes
  raw touch events into strokes of `(time, x, y)` with the coordinates as
  fractions of the screen, and `Device.play_gestures` scales them to whatever
  screen it is given. The old format stored digitizer coordinates - which is
  why replaying one elsewhere was refused - and replayed through `/dev/input`,
  which every recent Pixel denies to the shell, so it could not be replayed on
  the phone that made it either. The Windows front end records, plays, opens
  and saves.

- **A live view of the device screen**, in its own shape, with the strokes laid
  over exactly where they will land. `mthread.mirror.ScreenMirror` runs
  `com.mthread.Mirror` from the same jar as the injector: the phone scales and
  JPEG-compresses each frame, so the cable carries 27 kB instead of sixteen
  megabytes. About 3.4 frames a second on a Pixel 8 Pro, against one frame every
  two seconds for `adb exec-out screencap -p`.
- **Two sliders instead of five.** Edge sensitivity and detail were always
  turned together; speed and hand simulation were one axis pretending to be two.
  The margin is fixed at six per cent.
- The Windows front end connects by itself when there is exactly one device, and
  opens an image named on its command line.

- **The project is now MThread Draw.** Everything is renamed: `import adbtouch`
  becomes `import mthread`, `autodraw` becomes `mthread_draw`, the console
  script is `mthread` and the desktop entry point `mthread-draw`, the
  distribution on PyPI is `mthread-draw`, the installer is
  `MThreadDraw-x.y.z-x64.msi`, and the repository has moved to
  `github.com/MAXAWER/MThread-Draw` — GitHub redirects the old address, but
  update your remote. `AdbTouchError` is `MThreadError` and `ADBTOUCH_CACHE` is
  `MTHREAD_CACHE`. There is no compatibility shim: this predates any release
  under the old names other than a January pre-release of something else.
- `run.bat` could never fetch adb. Two backslashes had been lost from it long
  ago, leaving it looking for `platform-tools<BEL>db.exe` and calling
  `tools<FF>etch_platform_tools.py`.

- **Drawing works on devices that refuse raw touch events** - every recent
  Pixel, where SELinux denies the shell domain write access to `/dev/input`.
  `Device.supports_raw_touch` probes for it and the drawing path is picked
  accordingly, instead of reporting success and doing nothing.
- **An on-device injector** (`mthread/injector.py`, built from `injector/`),
  run once through `app_process` and fed points over stdin. One process for a
  whole drawing rather than one per point, which is what makes realistic timing
  possible at all. Measured on a Pixel 8 Pro: a 136-stroke, 1,679-point drawing
  in about 19 seconds, against 3 minutes 40 through `input`.
- **`mthread.hand`** simulates hand drawing: rounded corners, a velocity
  profile, tremor, overshoot and a sensible stroke order.
- **`mthread.paths`** joins the fragments `findContours` returns back into
  strokes and drops specks - 215 strokes became 136 on the sample image, which
  is both faster and cleaner.
- `tools/test_canvas.py`: a drawing canvas served to the device over
  `adb reverse`, with a calibration pattern, for checking any of this.
- Speed and hand-drawing controls in the desktop app, with a time estimate.

## 1.1.0

Packaging and presentation release; no behavioural changes to drawing or replay.

- **Installers.** A Windows `.msi` that installs like any other program, and a
  macOS `.dmg` for both Apple Silicon and Intel, built automatically from a tag.
- **Self-contained.** The packaged builds carry their own `adb`: no Android SDK,
  no platform-tools download, no `PATH` to edit. `find_adb` looks inside the
  bundle first, so an installed MThread Draw behaves the same everywhere.
- Packaged builds run a self-test before shipping, which imports the whole
  application and runs the bundled adb.
- Optional PyPI publishing through trusted publishing — see
  [docs/RELEASING.md](docs/RELEASING.md).
- `run.bat` and `run.sh`: one-click launchers that create the virtual
  environment and start the app.
- Generated demo assets (`docs/demo.gif`, `docs/pipeline.png`) produced from a
  real vectoriser run by `tools/make_demo.py`.
- Rewritten README: three-step quickstart, supported devices and emulators,
  supported image formats.
- Versioning continues from the old `v1.0` ADB Painter tag rather than
  restarting; `mthread` and `MThread Draw` share one version number.

## 0.2.0

- Split the `mthread` library out of the desktop app.
- Gesture recording and replay: `mthread record`, `mthread play`, and the
  Record tab in the app.
- Fixed touch mapping on devices whose digitizer resolution differs from the
  display resolution.

## 1.0 — ADB Painter

The original single-purpose build: load an image, draw it on the phone. Kept for
history; superseded by everything above.

# Changelog

## Unreleased

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

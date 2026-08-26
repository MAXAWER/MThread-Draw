# Changelog

## 1.1.0

Packaging and presentation release; no behavioural changes to drawing or replay.

- Tagged releases now build a standalone `AutoDraw.exe` and the Python
  distribution automatically, and attach both to the GitHub release.
- Optional PyPI publishing through trusted publishing — see
  [docs/RELEASING.md](docs/RELEASING.md).
- `run.bat` and `run.sh`: one-click launchers that create the virtual
  environment and start the app.
- Generated demo assets (`docs/demo.gif`, `docs/pipeline.png`) produced from a
  real vectoriser run by `tools/make_demo.py`.
- Rewritten README: three-step quickstart, supported devices and emulators,
  supported image formats.
- Versioning continues from the old `v1.0` ADB Painter tag rather than
  restarting; `adbtouch` and `AutoDraw` share one version number.

## 0.2.0

- Split the `adbtouch` library out of the desktop app.
- Gesture recording and replay: `adbtouch record`, `adbtouch play`, and the
  Record tab in the app.
- Fixed touch mapping on devices whose digitizer resolution differs from the
  display resolution.

## 1.0 — ADB Painter

The original single-purpose build: load an image, draw it on the phone. Kept for
history; superseded by everything above.

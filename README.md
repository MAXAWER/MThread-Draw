<div align="center">

<a href="https://maxawer.github.io/MThread-Draw/">
  <img src="docs/hero.svg" width="900" alt="MThread Draw — a motorcycle assembling itself out of touch strokes, one stroke at a time">
</a>

<sub>Not an illustration — 232 real strokes from <code>examples/motorcycle.jpg</code>, in the order they are sent to the phone.</sub>

<br><br>

<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/badge/%E2%AC%87_Windows-.msi-2563eb?style=for-the-badge&labelColor=0d1117" alt="Download for Windows"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/badge/%E2%AC%87_macOS-.dmg-2563eb?style=for-the-badge&labelColor=0d1117" alt="Download for macOS"></a>
<a href="https://maxawer.github.io/MThread-Draw/"><img src="https://img.shields.io/badge/%E2%96%B6_Try_it-in_your_browser-ffffff?style=for-the-badge&labelColor=0d1117" alt="Try it in your browser"></a>
<a href="README.ru.md"><img src="https://img.shields.io/badge/%F0%9F%87%B7%F0%9F%87%BA_%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B0%D1%8F_%D0%B2%D0%B5%D1%80%D1%81%D0%B8%D1%8F-README.ru.md-6b7280?style=for-the-badge&labelColor=0d1117" alt="Русская версия"></a>

<br>

<a href="https://github.com/MAXAWER/MThread-Draw/actions/workflows/ci.yml"><img src="https://github.com/MAXAWER/MThread-Draw/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/github/v/release/MAXAWER/MThread-Draw?include_prereleases&label=release&color=2563eb" alt="Latest release"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/licence-AGPL--3.0-2563eb" alt="Licence: AGPL-3.0"></a>
<img src="https://img.shields.io/badge/native-WinUI_3_%C2%B7_SwiftUI-6b7280" alt="Native front ends">

<br><br>

### Draws any picture on an Android screen by touching it.<br>Records and replays gestures. Nothing installed on the phone.

<sub>USB or wireless ADB · no root on most devices · no Android SDK · Python, OpenCV and adb travel inside the app</sub>

<br>

<img src="docs/demo.gif" width="760" alt="A photograph of a guitar traced into touch strokes and drawn on a phone screen">

<sub>57 strokes, 478 points — the exact path list sent to the device. Under two seconds on a Pixel 8 Pro.</sub>

</div>

## Start

| | |
|---|---|
| **1** | Install: [Windows `.msi`](https://github.com/MAXAWER/MThread-Draw/releases/latest) · [macOS `.dmg`](https://github.com/MAXAWER/MThread-Draw/releases/latest) · Linux — [from source](#from-source). Unsigned, so Windows says "unknown publisher" once and macOS wants right-click → **Open**. |
| **2** | On the phone: Settings → About phone → **Build number** ×7 → Developer options → **USB debugging**. Plug in, or `adb connect 192.168.1.42:5555`. |
| **3** | Open it. Drag the drawing over the live screen, wheel to resize, Shift+wheel to turn — **START DRAWING**. |

## What it does

| | |
|---|---|
| **Place it by hand** | Drag, resize, turn, flip, `Fit`. Held in fractions of the screen, so it survives the phone being turned. |
| **Layers** | Several pictures at once, each with its own placement and tracer settings. |
| **Erase strokes** | Drag across the lines you do not want; `Undo erase` brings them back. |
| **Re-trace in place** | The detail slider re-traces what is loaded — no reopening the file. |
| **Record and replay** | The file holds fractions of the screen, so it **replays on a different phone**, at any speed. |
| **Two tracers** | Canny for machines and buildings, flow-based coherent lines for faces and animals. The app asks what is in the picture, not which algorithm. |
| **Native windows** | WinUI 3 on Windows, SwiftUI on macOS, both driving one shared engine. |
| **No live view?** | A screenshot copied off the phone by hand will do — its proportions are what placement needs. |

```bash
mthread shape heart               # a heart, fitted to the screen
mthread text "hello" --y 0.35     # any font this machine has
mthread record -o login.json      # then: mthread play login.json --speed 2
```

```python
from mthread import Device
Device().draw_paths([[(100, 200), (400, 200), (400, 600)]])
```

<div align="center">
<img src="docs/examples.png" width="820" alt="Four photographs and the line drawings traced from them">

<sub>The files in <a href="examples/"><code>examples/</code></a>, resized and otherwise untouched — nothing prepared, retouched or masked.</sub>
</div>

## Why it is fast

`adb shell input tap` starts a process on the device per call, 100–300 ms each.
This sends the whole drawing at once instead, and a stroke that takes 40 seconds
through `input swipe` finishes in well under a second.

**[How it works →](docs/INTERNALS.md)** — the digitizer's own coordinate space,
the three ways into a device and why a recent Pixel refuses the fast one, what
"instant" actually costs, drawing like a hand, and the open ends.

<details>
<summary><b>Command line</b></summary>

<br>

```bash
mthread devices                       # what is attached
mthread info                          # screen size and digitizer ranges

mthread shape star --points 7 --rotate 20   # heart, star, circle, square, polygon, spiral, wave
mthread text "signed" --font arial.ttf --scale 0.5 --y 0.8
mthread play session.json --speed 0.5 --repeat 3
```

Every drawing command shares the placement options `--scale`, `--rotate`,
`--flip-x`, `--flip-y`, `--x`, `--y`, `--margin`, and `--speed`/`--human` for how
it draws.

Text is rendered with a real font and then traced, which is why any font works
and why letters come out as outlines: a filled glyph has an inside and an
outside, and this draws with one finger.

</details>

<a name="from-source"></a>
<details>
<summary><b>From source</b>, and building the apps yourself</summary>

<br>

[`run.bat`](run.bat) on Windows and [`run.sh`](run.sh) elsewhere do everything:
environment, dependencies, and `adb` if the machine has none. By hand:

```bash
git clone https://github.com/MAXAWER/MThread-Draw.git && cd MThread-Draw
pip install -e .            # library only - no dependencies at all
pip install -e ".[draw]"    # + image tracing (OpenCV, NumPy, Pillow)
```

`adb` is looked for in `ADB_PATH`, inside a packaged build, your `PATH`, a
`platform-tools` folder beside the working directory, then the usual SDK
locations — or `python tools/fetch_platform_tools.py` fetches it, 7 MB from
Google.

```bash
pip install pyinstaller
python tools/build_app.py --msi     # Windows: engine, WinUI front end, installer
python tools/build_macos.py --dmg   # macOS: bundle and disk image
```

The installer needs WiX: `dotnet tool install --global wix --version 5.0.2`.
Details in [RELEASING.md](docs/RELEASING.md).

</details>

<details>
<summary><b>Limits</b>, and what to do when touches land in the wrong place</summary>

<br>

- **A recording does not know which way up the phone was** — replay in the
  orientation you recorded in. Drawing itself does follow the orientation.
- **Replay has a fixed overhead** of a second or two for the on-device injector:
  the strokes and gaps are faithful, the total is not.
- **Stop is not instantaneous.** It cancels what is not yet queued; the device
  finishes the two seconds it already has.
- **Recordings from before 1.2 are not portable** and say so rather than
  misfiring.
- **Start with `mthread info`.** Then open an issue — templates for
  [bugs](https://github.com/MAXAWER/MThread-Draw/issues/new?template=bug_report.md)
  and [devices](https://github.com/MAXAWER/MThread-Draw/issues/new?template=device_report.md).
  Digitizer ranges differ wildly between panels, and only what people report can
  be fixed.

Works with any device `adb devices` lists, and with emulators that expose an ADB
port — AVD, BlueStacks, LDPlayer (`:5555`), Nox (`:62001`), MEmu (`:21503`).
PNG, JPEG, BMP, WebP. Python 3.9+.

</details>

## Licence

**AGPL-3.0, with a commercial licence available from the author.** Free to use,
change and share — but anything you **distribute**, or **run as a service**
others use, must publish its complete source under the AGPL, a rebranded copy
included. For a product whose source stays closed,
[ask for a commercial licence](https://github.com/MAXAWER/MThread-Draw/issues/new?title=Licence%20request).
Binding text: [LICENSE](LICENSE) · plain language: [TERMS.md](TERMS.md) ·
contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

<div align="center">
<br>
<b>If this saved you an afternoon, a ⭐ is how anyone else finds it.</b>
</div>

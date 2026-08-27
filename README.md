<div align="center">

<a href="https://maxawer.github.io/MThread-Draw/">
  <img src="docs/hero.svg" width="900" alt="MThread Draw — a motorcycle assembling itself out of touch strokes, one stroke at a time">
</a>

<sub>The drawing above draws itself, and it is not an illustration: those are the 232 strokes<br>
<a href="tools/make_hero.py"><code>tools/make_hero.py</code></a> gets out of <code>examples/motorcycle.jpg</code>, in the order the program sends them to a phone.</sub>

<br><br>

<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/badge/%E2%AC%87_Windows-installer_(.msi)-0d1117?style=for-the-badge&labelColor=0d1117&color=2563eb" alt="Download for Windows"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/badge/%E2%AC%87_macOS-disk_image_(.dmg)-0d1117?style=for-the-badge&labelColor=0d1117&color=2563eb" alt="Download for macOS"></a>
<a href="https://maxawer.github.io/MThread-Draw/"><img src="https://img.shields.io/badge/%E2%96%B6_Try_it-in_your_browser-0d1117?style=for-the-badge&labelColor=0d1117&color=ffffff" alt="Try it in your browser"></a>

<br>

<a href="https://github.com/MAXAWER/MThread-Draw/actions/workflows/ci.yml"><img src="https://github.com/MAXAWER/MThread-Draw/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/github/v/release/MAXAWER/MThread-Draw?include_prereleases&label=release&color=2563eb" alt="Latest release"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases"><img src="https://img.shields.io/github/downloads/MAXAWER/MThread-Draw/total?label=downloads&color=2563eb" alt="Downloads"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/licence-AGPL--3.0-2563eb" alt="Licence: AGPL-3.0"></a>
<img src="https://img.shields.io/badge/native-WinUI_3_%C2%B7_SwiftUI-6b7280" alt="Native front ends">
<a href="README.ru.md"><img src="https://img.shields.io/badge/%F0%9F%87%B7%F0%9F%87%BA_%D0%BF%D0%BE--%D1%80%D1%83%D1%81%D1%81%D0%BA%D0%B8-README.ru.md-6b7280" alt="По-русски"></a>

<br><br>

### It draws pictures on an Android screen by touching it,<br>and it records and replays gestures. Nothing is installed on the phone.

<sub><b>USB or wireless ADB · no root on most devices · no Android SDK · one download, everything inside</b></sub>

<br>

<img src="docs/demo.gif" width="820" alt="A colour photograph of a guitar being traced into touch strokes and drawn on a phone screen">

<sub>A photograph in, 57 strokes and 478 touch points out — the exact path list sent to the device.<br>
On a Pixel 8 Pro that draws in under two seconds.</sub>

</div>

---

## In about a minute

|  |  |
|---|---|
| **1 · Install** | [**Windows**](https://github.com/MAXAWER/MThread-Draw/releases/latest) — `MThreadDraw-x.y.z-x64.msi`, Start Menu entry and uninstaller included. [**macOS**](https://github.com/MAXAWER/MThread-Draw/releases/latest) — `.dmg` for Apple Silicon or Intel, drag it to Applications. **Linux** — the command line, [from source](#from-source). |
| **2 · Wake the phone** | Settings → About phone → tap **Build number** seven times → Developer options → **USB debugging**. Plug it in, or `adb connect 192.168.1.42:5555`. |
| **3 · Draw** | It finds the phone, shows the screen live, and lays the drawing over exactly where it will land. Drag to move, wheel to resize, Shift and wheel to turn — then **START DRAWING**. |

**Nothing else to install.** Python, OpenCV and **adb** all travel inside the
application. Both windows are native — **WinUI 3** on Windows, **SwiftUI** on
macOS — and each drives the same engine over a pipe, so neither has its own idea
of how anything works. The builds are not signed: SmartScreen says "unknown
publisher" once, and macOS wants a right-click → **Open** the first time.

---

## What the window lets you do

|  |  |
|---|---|
| **Place it exactly** | Drag the drawing across the live view; wheel resizes, Shift and wheel turns, `Flip` mirrors, `Fit` starts over. Held in fractions of the screen, so it survives the phone being turned. |
| **Layers** | Several pictures arranged against each other, each with its own placement and its own tracer settings. Hide one, reorder them, remove one. |
| **Erase single strokes** | Drag across the lines you do not want with the eraser on; `Undo erase` brings them back. |
| **Re-trace in place** | The detail slider re-traces what is already loaded. No need to open the file again. |
| **Record and replay** | Press record, do something on the phone, press stop. The file holds fractions of the screen, so it **replays on a different phone**, at any speed, any number of times. |
| **No live view?** | If capture fails, a screenshot you copied off the phone by hand will do: it does not update, but its proportions are what placement needs. |

Nothing to prepare, from the command line or from code:

```bash
mthread shape heart               # a heart, fitted to the screen
mthread text "hello" --y 0.35     # words, in any font this machine has
mthread record -o login.json      # then: mthread play login.json --speed 2
```

```python
from mthread import Device
Device().draw_paths([[(100, 200), (400, 200), (400, 600)]])
```

---

## How a photograph becomes touches

<div align="center">
<img src="docs/pipeline.png" width="860" alt="Source photograph, the lines the tracer finds, and the resulting stroke paths">
</div>

A tracer decides where the lines are, the result is thinned to one pixel wide,
and each line is walked into a single stroke — not an outline *around* the line,
which is what draws everything twice. Above is `examples/guitar.jpg`, untouched:
57 strokes, 478 points.

The app asks what is in the picture rather than which algorithm you would like:

| What you say is in it | What runs | Why that one |
|---|---|---|
| **Buildings, machines, objects** | Canny edges, thinned, walked into strokes | Keeps every bit of structure an edge detector sees — which is what a machine or a building is made of. |
| **Portraits, animals, nature** | Flow-based coherent lines, after Kang, Lee and Chui | Works out the direction each line runs in and filters along it: calmer, longer strokes, and a face stays a face. |

Neither wins everywhere, which is why both are here. Colour is what gets lost —
a finger draws one black line, so the output is always a line drawing.

<div align="center">
<img src="docs/examples.png" width="860" alt="Four photographs and the line drawings traced from them: a guitar, a motorcycle, a cat and a lighthouse">

<sub>Nothing prepared, retouched or masked — the files in <a href="examples/"><code>examples/</code></a>, resized and otherwise untouched.<br>
The only thing that differs between the columns is the two sliders every user has.</sub>
</div>

---

## Why it exists

`adb shell input tap` spawns a process on the device for every call. At
100–300 ms each, anything continuous — a gesture, a line, a test script — is
unusably slow. `mthread` gets the whole drawing onto the device in one go
instead: kernel events through a single pushed script where the phone allows it,
and a 3 KB injector run through `app_process` where it does not. A stroke that
takes 40 seconds through `input swipe` finishes in well under a second.

Two pieces, and either works without the other: **`mthread`**, a Python library
for synthetic touch input whose core has no dependencies at all, and **MThread
Draw**, the desktop application on top of it.

**[How it works, in detail →](docs/INTERNALS.md)** — the digitizer's own
coordinate space, the three ways into a device and why a recent Pixel refuses
the fast one, what "instant" costs, and how it draws like a hand.

---

## What it works with

|  |  |
|---|---|
| **Devices** | Anything `adb devices` lists, over USB or wireless ADB. Root is not needed on most devices. |
| **Emulators** | Android Studio AVD, BlueStacks (`:5555`), LDPlayer (`:5555`), Nox (`:62001`), MEmu (`:21503`). Raw `/dev/input` support differs between builds — `mthread info` says which path yours gets, and [device reports](https://github.com/MAXAWER/MThread-Draw/issues/new?template=device_report.md) are welcome. |
| **Images** | PNG, JPEG, BMP, WebP. Raster only for now. |
| **Host** | Windows, macOS, Linux. Python 3.9+. |

Used for drawing games and canvases, signatures and stamps, QA passes that
replay a recorded flow against every build, and repetitive tapping in apps with
no other automation hook. Whether automating a particular game is allowed is
between you and that game's rules; this is a general-purpose input tool.

<a name="from-source"></a>
<details>
<summary><b>From source</b>, and building the applications yourself</summary>

<br>

[`run.bat`](run.bat) on Windows and [`run.sh`](run.sh) elsewhere do the whole
thing: virtual environment, dependencies, and `adb` if the machine has none.
Otherwise:

```bash
git clone https://github.com/MAXAWER/MThread-Draw.git
cd MThread-Draw

pip install -e .            # library only - no dependencies at all
pip install -e ".[draw]"    # + image tracing (OpenCV, NumPy, Pillow)
pip install -e ".[bg]"      # + rembg background removal
```

`adb` is found in this order: `ADB_PATH`, the copy inside a packaged build, your
`PATH`, a `platform-tools` directory beside the working directory, then the usual
Android SDK locations. If you have none of those,
`python tools/fetch_platform_tools.py` fetches it — 7 MB, straight from Google.

```bash
pip install pyinstaller
python tools/build_app.py --msi     # Windows: engine, WinUI front end, installer
python tools/build_macos.py --dmg   # macOS: the bundle and its disk image
```

The installer needs WiX: `dotnet tool install --global wix --version 5.0.2`.
[Releasing](docs/RELEASING.md) covers the rest.

</details>

<details>
<summary><b>Command line</b> — every command, and the options they share</summary>

<br>

```bash
mthread devices                       # what is attached
mthread info                          # screen size and digitizer ranges

mthread shape heart                   # heart, star, circle, square, polygon, spiral, wave
mthread shape star --points 7 --rotate 20
mthread text "hello world"            # any font the machine has
mthread text "signed" --font arial.ttf --scale 0.5 --y 0.8

mthread record -o session.json        # record until Enter
mthread play session.json --speed 0.5 --repeat 3
```

Every drawing command takes the same placement options — `--scale`, `--rotate`,
`--flip-x`, `--flip-y`, `--x`, `--y`, `--margin` — and `--speed`/`--human` for
how it draws.

Text is rendered with a real font and then traced, which is why any font works
and why letters come out as outlines: a filled glyph is a shape with an inside
and an outside, and this draws with one finger.

</details>

<details>
<summary><b>Library</b> — the whole API in ten lines</summary>

<br>

```python
from mthread import Device, Recorder, Session, replay

device = Device()
print(device.screen_size, device.touch_device.path)

recorder = Recorder(device)
recorder.start()
input("Do something on the phone, then press Enter...")
recorder.stop().save("flow.json")

replay(device, Session.load("flow.json"), speed=2.0, repeat=10)
```

</details>

<details>
<summary><b>Known limits</b>, said plainly</summary>

<br>

- **A recording does not know which way up the phone was.** Drawing follows the
  orientation; a recording holds fractions of the screen it was made on, so a
  portrait recording replayed in landscape lands sideways.
- **Replay carries a fixed overhead.** Starting and stopping the on-device
  injector costs a second or two: the strokes and the gaps are faithful, the
  total is not.
- **Stop is not instantaneous.** It cancels what has not been queued yet and the
  device finishes what it already has — about two seconds' worth.
- **Recordings from before 1.2 are not portable** and say so rather than
  misfiring.
- **`mthread info` is the first thing to check** when touches land in the wrong
  place.

</details>

---

## Help, and helping

Something not working? Open an issue — there are templates for
[bugs](https://github.com/MAXAWER/MThread-Draw/issues/new?template=bug_report.md)
and [device reports](https://github.com/MAXAWER/MThread-Draw/issues/new?template=device_report.md).
Paste the output of `mthread info`; digitizer ranges differ wildly between
panels, and only what people report can be handled.

Contributions welcome — [CONTRIBUTING.md](CONTRIBUTING.md), and
[`good first issue`](https://github.com/MAXAWER/MThread-Draw/labels/good%20first%20issue)
is the easiest way in. [What is worth doing next →](docs/INTERNALS.md#open-ends)

## Licence

**AGPL-3.0, with a commercial licence available from the author.** Use it, change
it, share it, free of charge — but a version you **distribute**, or **run as a
service** other people use, has to publish its complete source under the AGPL
too, a rebranded copy included. To put it inside a product whose source stays
closed, [ask for a commercial licence](https://github.com/MAXAWER/MThread-Draw/issues/new?title=Licence%20request).

Binding text: [LICENSE](LICENSE). Plain language, English and Russian:
**[TERMS.md](TERMS.md)**.

<div align="center">
<br>
<b>If this saved you an afternoon, a ⭐ costs nothing and is how anyone else finds it.</b>
</div>

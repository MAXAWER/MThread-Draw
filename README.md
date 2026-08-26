<h1 align="center">AutoDraw&nbsp;+&nbsp;adbtouch</h1>

<p align="center">
  <b>Draw any picture on an Android screen, and record and replay touch gestures.</b><br>
  Over USB or wireless ADB. Nothing is installed on the phone.
</p>

<p align="center">
  <a href="https://github.com/MAXAWER/AutoDraw-Sim/actions/workflows/ci.yml"><img src="https://github.com/MAXAWER/AutoDraw-Sim/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Windows | macOS | Linux">
  <a href="https://github.com/MAXAWER/AutoDraw-Sim/stargazers"><img src="https://img.shields.io/github/stars/MAXAWER/AutoDraw-Sim?style=flat&label=stars" alt="Stars"></a>
</p>

<p align="center">
  <img src="docs/demo.gif" width="300" alt="An image being traced into touch strokes and drawn on a phone screen">
</p>

<p align="center">
  <sub>38 strokes, 950 touch points — the exact path list <code>adbtouch</code> sends to the device, animated in the order it draws them.<br>
  Rendered from a real run of the vectoriser by <a href="tools/make_demo.py"><code>tools/make_demo.py</code></a>; playback speed here is arbitrary.</sub>
</p>

---

## In three steps

```bash
# 1. Install (Python 3.9+, plus `adb` on your PATH)
git clone https://github.com/MAXAWER/AutoDraw-Sim.git
cd AutoDraw-Sim
pip install -e ".[gui]"

# 2. Plug the phone in with USB debugging on - or connect over Wi-Fi
adb connect 192.168.1.42:5555     # optional, wireless
adbtouch devices                  # should list your phone

# 3. Start the app
autodraw
```

In the app: **Connect device** → **Capture screen** → **Load image** → drag it over
the phone preview → **START DRAWING**.

No GUI, no clicking:

```python
from adbtouch import Device
Device().draw_paths([[(100, 200), (400, 200), (400, 600)]])
```

---

## How an image becomes touches

<p align="center">
  <img src="docs/pipeline.png" width="900" alt="Source image, detected edges, and the resulting stroke paths">
</p>

Feed it an ordinary picture. Edges are detected with Canny, contours are traced,
retraced double lines are collapsed, and what is left is a list of polylines.

Line art works best. A photo gives you its edges, which is usually not what you
wanted — the *Edge sensitivity* and *Detail* sliders are there to tune that, and
an optional background remover (`rembg`) helps with portraits and product shots.

---

## What it works with

| | |
|---|---|
| **Devices** | Any Android phone or tablet that `adb devices` lists — over USB, or wireless ADB (`adb connect <ip>:5555`). Root is not needed on most devices. |
| **Emulators** | Anything exposing an ADB port: Android Studio AVD, BlueStacks (`:5555`), LDPlayer (`:5555`), Nox (`:62001`), MEmu (`:21503`). Raw `/dev/input` support differs between builds — `adbtouch info` tells you in one line, and [device reports](https://github.com/MAXAWER/AutoDraw-Sim/issues/new?template=device_report.md) are welcome. |
| **Image formats** | PNG, JPEG, BMP, WebP. Raster only for now; SVG input is [an open task](https://github.com/MAXAWER/AutoDraw-Sim/issues). |
| **Host** | Windows, macOS, Linux. Python 3.9+. |

## What people use it for

- **Drawing games and canvases on the phone** — Gartic Phone, Skribbl.io, sketch
  chats, whiteboards, notes apps: anything where the picture has to be produced by
  an actual finger on the glass.
- **Signatures and stamps** you would otherwise redraw by hand every time.
- **QA and regression passes** — record a login flow once, replay it against every
  build, at 2x, ten times in a row.
- **Repetitive tapping** in apps that offer no other automation hook.

Whether automating a particular game is allowed is between you and that game's
rules; this is a general-purpose input tool.

---

## Why this exists

`adb shell input tap` spawns a process on the device for every single call. At
100–300 ms each, anything continuous — a gesture, a drawn line, a test script —
is unusably slow.

`adbtouch` writes raw kernel input events into `/dev/input` through **one** pushed
shell script instead. A stroke that takes 40 seconds through `input swipe`
finishes in well under a second. That single difference is what makes both
gesture replay and image drawing practical.

This repository is two things:

- **`adbtouch`** — a small Python library for fast synthetic touch input on Android
  over ADB. Records gestures, replays them, drives raw `/dev/input` events. Pure
  standard library; the core has no dependencies at all.
- **`AutoDraw`** — a desktop app built on it, for people who would rather click
  buttons than write code.

---

## Record and replay gestures

Press record, do something on the phone, press stop. You get a JSON file with
every touch event and its timing. Replay it whenever you want, at whatever speed.

```bash
adbtouch record -o login.json      # do the thing on the phone, press Enter
adbtouch play login.json --speed 2 --repeat 5
```

Useful for regression passes, for reproducing a bug reliably, or for any
repetitive tapping you would rather not do by hand.

## Install variants

You need [Android platform-tools](https://developer.android.com/tools/releases/platform-tools)
(`adb`) on your `PATH`, and USB debugging enabled on the phone:
Settings → About phone → tap *Build number* seven times → Developer options →
*USB debugging*.

```bash
pip install -e .            # library only - no dependencies at all
pip install -e ".[draw]"    # + image vectorisation (OpenCV, NumPy, Pillow)
pip install -e ".[gui]"     # + the desktop app
pip install -e ".[bg]"      # + rembg background removal
```

If `adb` is installed somewhere unusual, point `ADB_PATH` at it. On Windows you
can also just run [`run.bat`](run.bat), which creates a virtual environment and
starts the app for you; on macOS and Linux, [`run.sh`](run.sh).

## Command line

```bash
adbtouch devices                       # what is attached
adbtouch info                          # screen size and digitizer ranges
adbtouch record -o session.json        # record until Enter
adbtouch record -o session.json -d 30  # record for 30 seconds
adbtouch play session.json             # replay once
adbtouch play session.json --speed 0.5 --repeat 3
```

## Library

```python
from adbtouch import Device, Recorder, Session, replay

device = Device()
print(device.screen_size, device.touch_device.path)

recorder = Recorder(device)
recorder.start()
input("Do something on the phone, then press Enter...")
recorder.stop().save("flow.json")

replay(device, Session.load("flow.json"), speed=2.0, repeat=10)
```

---

## How it works

**Batched events.** Every stroke becomes a list of `sendevent` lines, written to a
temporary script, pushed once to `/data/local/tmp`, executed, and deleted. One ADB
round trip instead of thousands.

**Coordinate translation.** The touchscreen digitizer has its own coordinate
space, and on many phones it is *not* the display resolution — a 1080-pixel-wide
screen commonly sits on a 4096-step digitizer. Sending display pixels straight to
`sendevent` puts the touch in the wrong place. `adbtouch` reads the real axis
ranges from `getevent -pl` and rescales. Run `adbtouch info` to see yours.

**Retrace removal.** `findContours` walks the *boundary* of a region, and Canny
turns one pen stroke into two parallel edges — so the naive path traces up one
side of every line and back down the other, drawing everything twice.
`dedupe_retrace` detects when a contour's two halves are the same stroke and keeps
one of them, while leaving genuine closed shapes like circles intact.

---

## Known limits

- **Recordings are not portable between phones.** They contain raw digitizer
  coordinates, so replaying a recording made on a different panel is refused
  rather than silently misfiring.
- **Rotation is not handled.** Record and replay in the same orientation.
- **Some devices expose no touchscreen usable by `sendevent`.** Drawing then fails
  with an explicit error instead of a wrong result; `Device.swipe()` still works,
  and an automatic fallback is an open task.
- **`adbtouch info` is the first thing to check** when touches land in the wrong
  place.

---

## Open ends

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Issues labelled
[`good first issue`](https://github.com/MAXAWER/AutoDraw-Sim/labels/good%20first%20issue)
are the easiest way in. Things worth doing:

- SVG input, so line art skips edge detection entirely.
- Auto-detect swapped X/Y axes (the `swap_xy` flag exists but nothing sets it).
- Rotation-aware coordinate mapping.
- An automatic `input swipe` fallback when raw touch is unavailable.
- Trim recordings visually in the app; cut dead time at the start and end.
- Assertions during replay — wait for a screenshot to match before continuing,
  which is what turns this into a real test runner.
- Skeletonise edges instead of halving contours, for cleaner line art.
- Pressure-sensitive strokes from image darkness.

---

## If something does not work

Open an issue — there are templates for
[bugs](https://github.com/MAXAWER/AutoDraw-Sim/issues/new?template=bug_report.md)
and for [device reports](https://github.com/MAXAWER/AutoDraw-Sim/issues/new?template=device_report.md).
Touches landing in the wrong place, a phone that refuses to connect, an emulator
behaving differently — paste the output of `adbtouch info` and it is usually a
short fix. Digitizer ranges differ wildly between panels, and only what people
report can be handled.

**If this saved you an afternoon, a ⭐ costs nothing and is how anyone else finds
it.**

## License

MIT — see [LICENSE](LICENSE).

---

<details>
<summary><b>По-русски</b></summary>

## Что это

Инструмент, который **рисует картинки на экране Android** и **записывает и
повторяет жесты** — по USB или беспроводному ADB, без установки чего-либо на сам
телефон.

Две части в одном репозитории:

- **`adbtouch`** — библиотека для быстрого синтетического ввода касаний на Android
  через ADB. Записывает жесты, воспроизводит их, работает с событиями
  `/dev/input` напрямую. Ядро не требует зависимостей.
- **`AutoDraw`** — десктопное приложение поверх неё, для тех, кто предпочитает
  кнопки коду.

## Три шага

```bash
# 1. Установка (нужен Python 3.9+ и `adb` в PATH)
git clone https://github.com/MAXAWER/AutoDraw-Sim.git
cd AutoDraw-Sim
pip install -e ".[gui]"

# 2. Подключить телефон с включённой отладкой по USB - или по Wi-Fi
adb connect 192.168.1.42:5555     # по желанию, беспроводное подключение
adbtouch devices                  # телефон должен появиться в списке

# 3. Запустить приложение
autodraw
```

В приложении: **Connect device** → **Capture screen** → **Load image** →
перетащить картинку на превью экрана → **START DRAWING**.

На Windows можно вместо этого запустить [`run.bat`](run.bat) — он сам создаст
виртуальное окружение и откроет приложение. На macOS и Linux — [`run.sh`](run.sh).

## Как картинка превращается в касания

Подаёте обычное изображение. Границы находятся детектором Кэнни, контуры
трассируются, двойные обводки схлопываются — на выходе список ломаных линий.

Лучше всего работает контурный рисунок. Из фотографии получатся её границы, что
обычно не то, чего хотелось: ползунки *Edge sensitivity* и *Detail* как раз для
настройки, а опциональное удаление фона (`rembg`) помогает с портретами и
предметной съёмкой.

## С чем работает

| | |
|---|---|
| **Устройства** | Любой телефон или планшет, который виден в `adb devices` — по USB или по Wi-Fi (`adb connect <ip>:5555`). На большинстве устройств root не нужен. |
| **Эмуляторы** | Всё, что открывает порт ADB: Android Studio AVD, BlueStacks (`:5555`), LDPlayer (`:5555`), Nox (`:62001`), MEmu (`:21503`). Поддержка сырого `/dev/input` отличается от сборки к сборке — `adbtouch info` покажет за одну строку. Отчёты о конкретных устройствах приветствуются. |
| **Форматы** | PNG, JPEG, BMP, WebP. Пока только растр; SVG — в списке задач. |
| **Хост** | Windows, macOS, Linux. Python 3.9+. |

## Зачем это нужно

`adb shell input tap` запускает отдельный процесс на устройстве при каждом
вызове — 100–300 мс на команду. Для чего-либо непрерывного это неприемлемо
медленно. `adbtouch` пишет события ядра напрямую через **один** сценарий,
загруженный на устройство. Штрих, который через `input swipe` рисуется 40 секунд,
здесь занимает меньше секунды.

## Что с этим делают

- **Рисовалки на телефоне** — Gartic Phone, Skribbl.io, скетч-чаты, заметки и
  доски: всё, где картинку нужно вывести пальцем по стеклу.
- **Подписи и штампы**, которые иначе приходится перерисовывать вручную.
- **Тестирование**: записали сценарий логина один раз — прогоняете на каждой
  сборке, на удвоенной скорости, десять раз подряд.
- **Однообразные нажатия** в приложениях, где других способов автоматизации нет.

Допустимо ли автоматизировать конкретную игру — вопрос её правил; это инструмент
ввода общего назначения.

## Командная строка

```bash
adbtouch devices                  # какие устройства подключены
adbtouch info                     # разрешение экрана и диапазоны тачскрина
adbtouch record -o session.json   # запись до нажатия Enter
adbtouch play session.json --speed 2 --repeat 5
```

Если `adb` установлен в нестандартное место — укажите путь в переменной
окружения `ADB_PATH`.

## Ограничения

- Записи **не переносятся между разными телефонами** — внутри сырые координаты
  тачскрина. Попытка воспроизвести запись на панели другого размера будет
  отклонена, а не выполнена криво.
- Поворот экрана не учитывается: записывайте и воспроизводите в одной ориентации.
- На части устройств тачскрин недоступен для `sendevent`. Тогда рисование
  завершится понятной ошибкой, а не кривым результатом; `Device.swipe()`
  продолжает работать, автоматический откат — в списке задач.
- Если касания попадают не туда — начните с `adbtouch info`.

## Если что-то не работает

Заведите issue — есть шаблоны для
[багов](https://github.com/MAXAWER/AutoDraw-Sim/issues/new?template=bug_report.md)
и для [отчётов об устройстве](https://github.com/MAXAWER/AutoDraw-Sim/issues/new?template=device_report.md).
Касания не туда, телефон не подключается, эмулятор ведёт себя иначе — приложите
вывод `adbtouch info`, обычно это чинится быстро. Диапазоны координат тачскрина у
разных панелей разные, и починить можно только то, что видно.

**Если инструмент сэкономил вам вечер — звезда ⭐ ничего не стоит, а найти проект
другим людям помогает.**

</details>

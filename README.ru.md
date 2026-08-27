<div align="center">

<a href="https://maxawer.github.io/MThread-Draw/">
  <img src="docs/hero.svg" width="900" alt="MThread Draw — мотоцикл, собирающийся из штрихов касаний">
</a>

<sub>Не иллюстрация — 232 настоящих штриха из <code>examples/motorcycle.jpg</code>, в том порядке, в котором они уходят на телефон.</sub>

<br><br>

<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/badge/%E2%AC%87_Windows-.msi-2563eb?style=for-the-badge&labelColor=0d1117" alt="Скачать для Windows"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/badge/%E2%AC%87_macOS-.dmg-2563eb?style=for-the-badge&labelColor=0d1117" alt="Скачать для macOS"></a>
<a href="https://maxawer.github.io/MThread-Draw/"><img src="https://img.shields.io/badge/%E2%96%B6_%D0%9F%D0%BE%D0%BF%D1%80%D0%BE%D0%B1%D0%BE%D0%B2%D0%B0%D1%82%D1%8C-%D0%B2_%D0%B1%D1%80%D0%B0%D1%83%D0%B7%D0%B5%D1%80%D0%B5-ffffff?style=for-the-badge&labelColor=0d1117" alt="Попробовать в браузере"></a>
<a href="README.md"><img src="https://img.shields.io/badge/%F0%9F%87%AC%F0%9F%87%A7_English_version-README.md-6b7280?style=for-the-badge&labelColor=0d1117" alt="English version"></a>

<br>

<a href="https://github.com/MAXAWER/MThread-Draw/actions/workflows/ci.yml"><img src="https://github.com/MAXAWER/MThread-Draw/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://github.com/MAXAWER/MThread-Draw/releases/latest"><img src="https://img.shields.io/github/v/release/MAXAWER/MThread-Draw?include_prereleases&label=%D1%80%D0%B5%D0%BB%D0%B8%D0%B7&color=2563eb" alt="Последний релиз"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/%D0%BB%D0%B8%D1%86%D0%B5%D0%BD%D0%B7%D0%B8%D1%8F-AGPL--3.0-2563eb" alt="Лицензия AGPL-3.0"></a>
<img src="https://img.shields.io/badge/%D0%BD%D0%B0%D1%82%D0%B8%D0%B2%D0%BD%D0%BE-WinUI_3_%C2%B7_SwiftUI-6b7280" alt="Нативные интерфейсы">

<br><br>

### Рисует любую картинку на экране Android, касаясь его.<br>Записывает и повторяет жесты. На телефон ничего не ставится.

<sub>USB или ADB по Wi-Fi · на большинстве устройств без root · без Android SDK · Python, OpenCV и adb лежат внутри приложения</sub>

<br>

<img src="docs/demo.gif" width="760" alt="Фотография гитары, превращённая в штрихи и нарисованная на экране телефона">

<sub>57 штрихов, 478 точек — ровно тот список путей, что уходит на устройство. На Pixel 8 Pro меньше двух секунд.</sub>

</div>

## Начать

| | |
|---|---|
| **1** | Установить: [Windows `.msi`](https://github.com/MAXAWER/MThread-Draw/releases/latest) · [macOS `.dmg`](https://github.com/MAXAWER/MThread-Draw/releases/latest) · Linux — [из исходников](#из-исходников). Подписи нет, поэтому Windows один раз скажет «неизвестный издатель», а macOS попросит правую кнопку → **Открыть**. |
| **2** | На телефоне: Настройки → О телефоне → **Номер сборки** ×7 → Для разработчиков → **Отладка по USB**. Подключить кабель или `adb connect 192.168.1.42:5555`. |
| **3** | Открыть. Тащить рисунок по живому экрану, колесо — размер, Shift+колесо — поворот, затем **START DRAWING**. |

## Что умеет

| | |
|---|---|
| **Размещение мышью** | Тащить, менять размер, поворачивать, отражать, `Fit`. Хранится в долях экрана и переживает поворот телефона. |
| **Слои** | Несколько картинок сразу, у каждой своё положение и свои настройки трассировки. |
| **Ластик по штрихам** | Провести по ненужным линиям; `Undo erase` возвращает их. |
| **Пересчёт на месте** | Ползунок детализации перетрассирует загруженное — заново открывать файл не нужно. |
| **Запись и повтор** | Файл хранит доли экрана, поэтому **воспроизводится на другом телефоне**, с любой скоростью. |
| **Два трассировщика** | Кэнни для техники и зданий, когерентные линии по потоку для лиц и животных. Приложение спрашивает, что на картинке, а не какой алгоритм. |
| **Нативные окна** | WinUI 3 на Windows, SwiftUI на macOS, оба поверх одного движка. |
| **Нет живого экрана?** | Подойдёт снимок, снятый на телефоне вручную — важны его пропорции. |

```bash
mthread shape heart               # сердце, вписанное в экран
mthread text "привет" --y 0.35    # любым шрифтом, что есть в системе
mthread record -o login.json      # затем: mthread play login.json --speed 2
```

```python
from mthread import Device
Device().draw_paths([[(100, 200), (400, 200), (400, 600)]])
```

<div align="center">
<img src="docs/examples.png" width="820" alt="Четыре фотографии и штриховые рисунки, полученные из них">

<sub>Это файлы из <a href="examples/"><code>examples/</code></a>, только уменьшенные — ничего не готовилось, не ретушировалось и не вырезалось.</sub>
</div>

## Почему это быстро

`adb shell input tap` запускает на устройстве отдельный процесс на каждый вызов —
100–300 мс за штуку. Здесь весь рисунок уходит целиком, и штрих, который через
`input swipe` рисуется 40 секунд, занимает меньше секунды.

**[Как это устроено →](docs/INTERNALS.md)** (по-английски) — своя система
координат у тачскрина, три пути внутрь устройства и почему свежий Pixel
отказывает в самом быстром, чего стоит «мгновенно», рисование по-человечески и
список открытых задач.

<details>
<summary><b>Командная строка</b></summary>

<br>

```bash
mthread devices                  # какие устройства подключены
mthread info                     # разрешение экрана и диапазоны тачскрина

mthread shape star --points 7 --rotate 20   # heart, star, circle, square, polygon, spiral, wave
mthread text "подпись" --font arial.ttf --scale 0.5 --y 0.8
mthread play session.json --speed 0.5 --repeat 3
```

У всех команд рисования общие параметры размещения `--scale`, `--rotate`,
`--flip-x`, `--flip-y`, `--x`, `--y`, `--margin` и `--speed`/`--human` — как
рисовать.

Текст рисуется настоящим шрифтом и затем трассируется: поэтому доступен любой
шрифт системы и поэтому буквы выходят контурами — у залитой глифы есть внутренняя
и внешняя граница, а здесь рисует один палец.

</details>

<a name="из-исходников"></a>
<details>
<summary><b>Из исходников</b> и как собрать приложения самому</summary>

<br>

[`run.bat`](run.bat) на Windows и [`run.sh`](run.sh) на macOS и Linux делают всё
сами: окружение, зависимости и `adb`, если своего нет. Вручную:

```bash
git clone https://github.com/MAXAWER/MThread-Draw.git && cd MThread-Draw
pip install -e .            # только библиотека - зависимостей нет вообще
pip install -e ".[draw]"    # + трассировка картинок (OpenCV, NumPy, Pillow)
```

`adb` ищется в `ADB_PATH`, внутри собранного приложения, в вашем `PATH`, в папке
`platform-tools` рядом с рабочим каталогом, затем в обычных путях SDK — или
`python tools/fetch_platform_tools.py` скачает его, 7 МБ от Google.

```bash
pip install pyinstaller
python tools/build_app.py --msi     # Windows: движок, интерфейс WinUI, установщик
python tools/build_macos.py --dmg   # macOS: бандл и образ диска
```

Установщику нужен WiX: `dotnet tool install --global wix --version 5.0.2`.

</details>

<details>
<summary><b>Ограничения</b> и что делать, если касания попадают не туда</summary>

<br>

- **Запись не знает, как был повёрнут телефон** — воспроизводите в той же
  ориентации, в которой записывали. Само рисование ориентацию учитывает.
- **У воспроизведения есть постоянная накладная стоимость** — секунда-две на
  инжектор: штрихи и паузы точны, общая длительность нет.
- **Стоп не мгновенный.** Он отменяет то, что ещё не отправлено; уже полученные
  две секунды устройство дорисует.
- **Записи старше 1.2 не переносятся** между телефонами и честно об этом
  сообщают, а не рисуют мимо.
- **Начните с `mthread info`.** Дальше — issue, есть шаблоны для
  [багов](https://github.com/MAXAWER/MThread-Draw/issues/new?template=bug_report.md)
  и [устройств](https://github.com/MAXAWER/MThread-Draw/issues/new?template=device_report.md).
  Диапазоны координат тачскрина у разных панелей разные, и починить можно только
  то, что видно.

Работает с любым устройством из `adb devices` и с эмуляторами, открывающими порт
ADB — AVD, BlueStacks, LDPlayer (`:5555`), Nox (`:62001`), MEmu (`:21503`).
PNG, JPEG, BMP, WebP. Python 3.9+.

</details>

## Лицензия

**AGPL-3.0 плюс коммерческая лицензия от автора.** Пользоваться, менять и
делиться — бесплатно, но всё, что вы **распространяете** или **держите сервисом**
для других, обязано публиковать полный исходный код под AGPL, включая
перекрашенную копию. Для продукта с закрытым кодом нужна
[коммерческая лицензия](https://github.com/MAXAWER/MThread-Draw/issues/new?title=Licence%20request).
Юридический текст: [LICENSE](LICENSE) · человеческим языком:
[TERMS.md](TERMS.md) · участие: [CONTRIBUTING.md](CONTRIBUTING.md).

<div align="center">
<br>
<b>Если инструмент сэкономил вам вечер — звезда ⭐ помогает найти его другим.</b>
</div>

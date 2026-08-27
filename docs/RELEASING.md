# Releasing

## Cutting a release

1. Bump the version in `pyproject.toml`, `mthread/__init__.py` and
   `mthread_draw/__init__.py` — all three carry the same number.
2. Add a section to [`CHANGELOG.md`](../CHANGELOG.md).
3. Commit, then tag and push:

   ```bash
   git tag v1.1.0
   git push origin main --tags
   ```

`.github/workflows/release.yml` takes it from there:

| Artifact | Built on |
|---|---|
| `MThreadDraw-<version>-x64.msi`, and the same application as a `.zip` | windows-latest |
| `MThreadDraw-<version>-arm64.dmg` | macos-latest |
| `MThreadDraw-<version>-x64.dmg` | macos-15-intel |
| sdist and wheel | ubuntu-latest |

Tags must start with `v`. Anything else is ignored by the workflow. The same
build jobs also run on any pull request that touches `packaging/`, the build
scripts or either front end, without publishing - packaging breaks quietly, and
only on the platform you are not developing on. For `macos/` that is not a
safety net but the only compiler it ever meets: there is no Mac on the
maintainer's desk, and the first commit of the Swift front end reached CI with
two errors in it.

## The Windows front end

`winui/` is a WinUI 3 application that draws the window and nothing else. It
launches the engine - `mthread_draw.server`, the same one every platform uses - as a
child process and speaks JSON lines to it over a pipe. That is what keeps one
implementation of tracing, ADB and touch injection rather than two.

```bash
python tools/build_app.py --winui
```

builds the engine as a console executable, publishes the front end
self-contained, and puts the engine inside it, so the result is a folder that
runs on a machine with nothing installed.

Two things about it are not obvious and cost an afternoon each:

- **Publishing loses the compiled XAML.** `App.xbf`, `MainWindow.xbf` and the
  resource index are written beside the assembly at build time and are not
  carried into the publish output, because an unpackaged project has no
  packaging tooling to nominate them. The app then dies inside
  `InitializeComponent` with a stowed exception that names nothing. The project
  copies them afterwards.
- **Windows App SDK 1.6 cannot build without Visual Studio**, because its PRI
  targets load MSBuild tasks that only ship with VS. Version 2.x does not, which
  is why the reference is pinned there.

## The macOS front end

`macos/` is a SwiftUI application, built as a Swift package rather than an Xcode
project so that `swift build` on a runner is the whole build with no project file
to keep in sync. `tools/build_macos.py` assembles the `.app` around the binary
and folds the engine into `Contents/Resources/engine`.

The glass is `NSVisualEffectView` with `behindWindow` blending, not SwiftUI's
`.ultraThinMaterial`: the material frosts what is behind it *inside* the window,
which on a plain background is a grey panel. Only the AppKit view samples the
desktop under the window, which is what the word glass means here.

Two things to know before touching it:

- **The deployment target is macOS 13**, and a modern SDK will happily compile
  macOS 14 API without a word until it reaches `swift build` on the runner. The
  argument-less `onChange(of:)` is the one that got in.
- **No file may be called `main.swift`**, because a file by that name is
  top-level code and cannot coexist with the `@main` attribute the app entry
  point uses.

## Building locally

```bash
pip install pyinstaller
python tools/build_app.py              # the engine alone
python tools/build_app.py --msi        # engine, WinUI front end, installer
python tools/build_macos.py --dmg      # macOS: the bundle and its disk image
```

Everything is built in a scratch directory outside the checkout, and only the
finished installer and zip are copied into `dist/`. This tree lives in OneDrive
on one machine, and a sync client holds handles on files while it uploads them:
writing several thousand of them into a synced folder failed at a different step
every time - deleting the last build, zipping a DLL, harvesting for the
installer - always with an access denied that named a file rather than a cause.

Each build runs the packaged app's own self-test (`MThread Draw --selftest`) before
it is considered finished: it imports the whole application and resolves and
runs the bundled adb. An incomplete bundle fails the build instead of failing on
a user's desktop - which is how `mthread.vectorize`, imported lazily through
`__getattr__` and therefore invisible to PyInstaller, was once left out.

### WiX

The Windows installer needs WiX **5**:

```bash
dotnet tool install --global wix --version 5.0.2
```

Version 6 and later refuse to build until you accept the Open Source Maintenance
Fee licence, which is not something a build script can do unattended.

## The bundled adb

The installers carry Google's `adb` inside them, fetched at build time by
`tools/fetch_platform_tools.py`, so that installing MThread Draw installs
everything. Two things worth knowing:

- platform-tools is published under the Android Software Development Kit
  licence, which restricts redistribution. Bundling it is a deliberate choice -
  the same one scrcpy and similar tools make - and `NOTICE.txt` ships beside the
  binary for that reason. To ship without it, build with `--no-adb`; the app
  then falls back to whatever adb the machine has, exactly like a source
  checkout.
- The bundled copy outranks `PATH`, so an installed MThread Draw behaves the same on
  every machine.

## Code signing

Nothing is signed. Windows SmartScreen will warn once, and macOS will refuse the
first launch until the user right-clicks and chooses Open. Signing needs an
Authenticode certificate (a few hundred a year) and, for macOS, an Apple
Developer account plus notarisation; the release notes tell users which button
to press instead.

## Publishing to PyPI

Publishing is opt-in, so a fork does not try to push to an index it has no
credentials for. Once:

1. Create a pending publisher at
   <https://pypi.org/manage/account/publishing/> for the project name
   `mthread`, owner `MAXAWER`, repository `MThread-Draw`, workflow
   `release.yml`, environment `pypi`.
2. Create the `pypi` environment under **Settings → Environments**.
3. Set the repository variable `PUBLISH_TO_PYPI` to `true` under
   **Settings → Secrets and variables → Actions → Variables**.

After that every `v*` tag publishes. No API token is stored anywhere.

Once the first upload lands, the install line in the README can become:

```bash
pip install mthread          # library
pip install mthread-draw    # + the engine the windows drive
```

## Version numbers

`mthread` and `MThread Draw` ship together and share one version. The tag `v1.0`
predates the rewrite and belongs to the old ADB Painter build, so releases
continue from `1.1.0` rather than restarting.

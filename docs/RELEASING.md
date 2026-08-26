# Releasing

## Cutting a release

1. Bump the version in `pyproject.toml`, `adbtouch/__init__.py` and
   `autodraw/__init__.py` — all three carry the same number.
2. Add a section to [`CHANGELOG.md`](../CHANGELOG.md).
3. Commit, then tag and push:

   ```bash
   git tag v1.1.0
   git push origin main --tags
   ```

`.github/workflows/release.yml` takes it from there:

| Artifact | Built on |
|---|---|
| `AutoDraw-<version>-x64.msi`, and the same app as a `.zip` | windows-latest |
| `AutoDraw-<version>-arm64.dmg` | macos-latest |
| `AutoDraw-<version>-x64.dmg` | macos-13 |
| sdist and wheel | ubuntu-latest |

Tags must start with `v`. Anything else is ignored by the workflow. The same
build jobs also run on any pull request that touches `packaging/` or the build
scripts, without publishing - packaging breaks quietly, and only on the platform
you are not developing on.

## The Windows front end

`winui/` is a WinUI 3 application that draws the window and nothing else. It
launches the engine - `autodraw.server`, the same one every platform uses - as a
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

## Building locally

```bash
pip install pyinstaller
python tools/build_app.py --msi        # Windows
python tools/build_app.py --dmg        # macOS
python tools/build_app.py --archive    # a plain zip / tar.gz anywhere
```

Each build runs the packaged app's own self-test (`AutoDraw --selftest`) before
it is considered finished: it imports the whole application and resolves and
runs the bundled adb. An incomplete bundle fails the build instead of failing on
a user's desktop - which is how `adbtouch.vectorize`, imported lazily through
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
`tools/fetch_platform_tools.py`, so that installing AutoDraw installs
everything. Two things worth knowing:

- platform-tools is published under the Android Software Development Kit
  licence, which restricts redistribution. Bundling it is a deliberate choice -
  the same one scrcpy and similar tools make - and `NOTICE.txt` ships beside the
  binary for that reason. To ship without it, build with `--no-adb`; the app
  then falls back to whatever adb the machine has, exactly like a source
  checkout.
- The bundled copy outranks `PATH`, so an installed AutoDraw behaves the same on
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
   `adbtouch`, owner `MAXAWER`, repository `AutoDraw-Sim`, workflow
   `release.yml`, environment `pypi`.
2. Create the `pypi` environment under **Settings → Environments**.
3. Set the repository variable `PUBLISH_TO_PYPI` to `true` under
   **Settings → Secrets and variables → Actions → Variables**.

After that every `v*` tag publishes. No API token is stored anywhere.

Once the first upload lands, the install line in the README can become:

```bash
pip install adbtouch          # library
pip install "adbtouch[gui]"   # + the desktop app
```

## Version numbers

`adbtouch` and `AutoDraw` ship together and share one version. The tag `v1.0`
predates the rewrite and belongs to the old ADB Painter build, so releases
continue from `1.1.0` rather than restarting.

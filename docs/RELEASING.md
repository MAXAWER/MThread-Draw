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

`.github/workflows/release.yml` takes it from there: it builds `AutoDraw.exe` on
a Windows runner, builds the sdist and wheel, and attaches all three to a GitHub
release with generated notes.

Tags must start with `v`. Anything else is ignored by the workflow.

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

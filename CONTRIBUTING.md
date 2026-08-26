# Contributing

Thanks for taking a look. This is a small project and every kind of help counts,
including bug reports from phones we cannot test on ourselves.

## Getting set up

```bash
git clone https://github.com/MAXAWER/MThread-Draw.git
cd MThread-Draw
python -m pip install -e ".[gui,dev]"
python -m unittest discover -s tests
```

The tests do not need a phone. Everything that touches hardware is behind a thin
seam, so the parsing, coordinate maths and script generation are all covered by
plain unit tests that run in under a second.

## Layout

| Path | What lives there |
| --- | --- |
| `mthread/` | The library: device control, touch events, recording, replay. No GUI imports. |
| `mthread/touch.py` | Input-event codes and the display-to-digitizer coordinate mapping. |
| `mthread/recorder.py` | Parsing `getevent -t` output into a session. |
| `mthread/player.py` | Turning a session back into a timed shell script. |
| `mthread/vectorize.py` | Image to stroke paths. The only module that needs OpenCV. |
| `mthread_draw/` | The desktop app. Keep logic out of here; put it in the library with a test. |
| `tests/` | Unit tests, standard library `unittest`, no pytest required. |

## Ground rules

- The library must keep working without OpenCV installed. Recording and replay
  are stdlib-only on purpose, so `pip install mthread` stays lightweight.
- Anything that can be tested without a phone should be. If you find yourself
  unable to test a change, that usually means the logic wants pulling out of the
  hardware path.
- Cross-platform: no hardcoded `.exe`, no backslash paths, no writing into the
  current working directory.
- Public functions get a docstring explaining *why*, not just what.

## Good first issues

Look for the [`good first issue`](https://github.com/MAXAWER/MThread-Draw/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
label. If none are open and you want something to do, the open ends listed at the
bottom of the README are all fair game.

## Reporting a device

If drawing lands in the wrong place on your phone, that is useful data. Open a
Device report issue with the output of `mthread info` - it prints the digitizer
ranges we need to see.

## Licensing of contributions

The project is AGPL-3.0 with a commercial licence available separately - see
[TERMS.md](TERMS.md). Dual licensing only works if one person holds the rights
to all of the code, so by opening a pull request you grant the author a
perpetual, worldwide, irrevocable, royalty-free licence to use, modify and
relicense your contribution as part of the project, including under that
commercial licence. You keep the copyright in what you wrote.

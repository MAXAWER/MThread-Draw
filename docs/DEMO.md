# Demo assets

`docs/demo.gif` and `docs/pipeline.png` in the README are generated, not drawn by
hand:

```bash
pip install -e ".[draw]"
python tools/make_sample.py examples/sample.png   # the line-art cat
python tools/make_demo.py                          # -> docs/demo.gif, docs/pipeline.png
```

`tools/make_demo.py` runs the real `Vectorizer` and animates the paths it
produces, in the order the device receives them. Point it at any image:

```bash
python tools/make_demo.py path/to/your.png --out docs
```

Nothing about the geometry is faked. What the animation cannot show is the phone
itself — the timing is arbitrary, and no device is involved.

## Recording the real thing

A screen recording of an actual phone is better, and takes about five minutes.
Mirror the device with [scrcpy](https://github.com/Genymobile/scrcpy), start
`autodraw`, record the mirror window, then cut it down:

```bash
# 1. Mirror the phone and record the window (scrcpy 2.x writes an mp4 directly)
scrcpy --record demo.mp4 --max-size 720

# 2. Draw something from AutoDraw while that runs, then stop scrcpy.

# 3. Trim to the interesting part and turn it into a GIF that is small enough
#    for a README - two-pass, so the palette does not fall apart.
ffmpeg -ss 3 -t 12 -i demo.mp4 -vf "fps=12,scale=320:-1:flags=lanczos,palettegen" palette.png
ffmpeg -ss 3 -t 12 -i demo.mp4 -i palette.png \
       -lavfi "fps=12,scale=320:-1:flags=lanczos[v];[v][1:v]paletteuse" docs/demo.gif
```

Keep the result under about 5 MB; GitHub serves it on every page view. If it is
larger, drop the frame rate to 10, the width to 280, or the clip to eight
seconds.

Speeding the clip up is fine — say so in the caption if you do.

# Demo assets

`docs/demo.gif`, `docs/pipeline.png` and `docs/examples.png` in the README are
generated, not drawn by hand:

```bash
pip install -e ".[draw]"
python tools/make_demo.py
```

That traces all four photographs in `examples/`, lays them out as the gallery,
animates one of them onto a phone, and renders the three-step pipeline picture.
`--hero guitar` animates a different one. Point it at an image of your own with:

```bash
python tools/make_demo.py --image path/to/your.jpg --method flow
```

Nothing about the geometry is faked: the strokes are what `Vectorizer` produces,
in the order the device receives them. What the animation cannot show is the
phone itself — the timing is arbitrary, and no device is involved.

## Two things that decide how the GIF looks

**Everything is drawn at three times the size and scaled back down.** A
one-pixel line drawn straight into the final image is a staircase, and a picture
full of staircases is most of why the first version of these assets looked
cheap.

**The photograph is dithered once, and every frame after that is quantised
without dithering.** Re-dithering each finished frame costs twice over: the
palette is recomputed per frame, so the photograph quietly boils as it plays,
and the error diffusion discovers that the pen's pure red is a decent
approximation of a cat's nose. Ink, pen and a grey ramp are appended to the
palette by hand afterwards, because median cut allocates colours by area and
none of the three covers enough of the picture to win a vote.

Saving with `disposal=1` rather than `disposal=2` is worth a factor of thirty in
file size — 6.8 MB down to 225 KB — because only the phone screen changes
between frames, and leaving the previous frame in place lets the encoder store
just that rectangle.

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

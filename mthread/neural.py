"""Edge detection by a neural network, for photographs an operator cannot fix.

Canny and the flow filters answer the same question: where does the picture
change. A photograph of something built answers that everywhere - every rivet,
every shadow, every patch of gravel - and no threshold separates the girder that
carries the shape from the gravel that does not, because the gravel often has
the stronger contrast.

DexiNed answers a different question: how likely is this to be an edge somebody
would draw. It was trained on edges people annotated, so its output is not a
yes or no but a ranking, and a threshold on a ranking drops the gravel and keeps
the girder. That is the whole reason to carry a model at all.

It runs through OpenCV's own DNN module, so nothing beyond OpenCV is needed, and
the weights come from the OpenCV Model Zoo under the MIT licence. They are
downloaded on request rather than shipped: 46 MB is a lot to impose on somebody
who only wanted to draw a stick figure, and everything here works without them.
"""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

import numpy as np

from .errors import MThreadError

__all__ = ["MODEL_URL", "model_path", "have_model", "download_model", "edge_probability"]

#: OpenCV's own conversion of DexiNed, MIT licensed, from their Model Zoo.
MODEL_URL = ("https://huggingface.co/opencv/edge_detection_dexined/resolve/main/"
             "edge_detection_dexined_2024sep.onnx")
MODEL_NAME = "edge_detection_dexined_2024sep.onnx"
MODEL_BYTES = 46 * 1024 * 1024  # approximate, for progress reporting

#: What the network was trained to expect: BGR, mean-subtracted, unscaled.
MEAN = (103.5, 116.2, 123.6)


class ModelUnavailableError(MThreadError):
    """The model is not downloaded, and nothing may download it silently."""


def cache_dir() -> Path:
    """Where a downloaded model lives.

    Not inside the package: a wheel should not grow by 46 MB, and a model that
    outlives an upgrade is a feature.
    """
    base = os.environ.get("MTHREAD_CACHE")
    if base:
        return Path(base)
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(root) / "mthread"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mthread"


def model_path() -> Path:
    return cache_dir() / MODEL_NAME


def have_model() -> bool:
    path = model_path()
    return path.is_file() and path.stat().st_size > 1_000_000


def download_model(progress=None) -> Path:
    """Fetch the weights, reporting progress as a fraction from 0 to 1.

    Downloaded to a temporary name and moved into place at the end, so an
    interrupted download cannot leave a half-file that looks installed.
    """
    destination = model_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".part")

    with urllib.request.urlopen(MODEL_URL) as response, partial.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or MODEL_BYTES)
        done = 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if progress is not None:
                progress(min(1.0, done / max(total, 1)))

    shutil.move(str(partial), str(destination))
    return destination


def edge_probability(image, path: Path | None = None):
    """Run the network over a BGR image and return a 0-1 edge probability map.

    The model takes any size that is a multiple of sixteen, and giving it the
    real one matters: fed a 512-pixel square and stretched back, a lattice tower
    loses exactly the fine structure that makes it recognisable.
    """
    import cv2  # imported late: the core library has no imaging dependencies

    path = Path(path) if path else model_path()
    if not path.is_file():
        raise ModelUnavailableError(
            f"The edge-detection model is not downloaded. Expected it at {path}. "
            "Call download_model(), or use one of the methods that needs no model."
        )

    height, width = image.shape[:2]
    fitted = cv2.resize(image, (width // 16 * 16, height // 16 * 16),
                        interpolation=cv2.INTER_AREA)

    net = cv2.dnn.readNetFromONNX(str(path))
    net.setInput(cv2.dnn.blobFromImage(fitted, 1.0, (fitted.shape[1], fitted.shape[0]),
                                       MEAN, swapRB=False, crop=False))
    raw = np.squeeze(net.forward())

    probability = 1.0 / (1.0 + np.exp(-raw))
    spread = probability.max() - probability.min()
    if spread > 0:
        probability = (probability - probability.min()) / spread
    return cv2.resize(probability, (width, height))

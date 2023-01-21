import numpy as np
from scipy.signal import convolve2d
from skimage.feature import peak_local_max


def analog(img, dark, *args, **kwargs):
    buf = img - dark
    return buf


def thresholding(img, dark, *args, **kwargs):
    if kwargs["th"] is None:
        pass
    buf = img - dark
    buf = buf > kwargs["th"]
    return buf


def counting(img, dark, *args, **kwargs):
    kernel = np.ones([2, 2])
    th = 999  # big value to show that the threshold is not given loaded
    if kwargs.get("th") is not None:
        th = kwargs.get("th")
    buf = img - dark  # pedestal subtraction
    buf = (buf > 0) * buf  # take only positive values
    clusters = convolve2d(img, kernel, mode="same", fillvalue=0)  # clusters
    local_maxima = peak_local_max(clusters, min_distance=1, threshold_abs=th)
    mask = np.zeros([400, 400], dtype=float)
    mask[tuple(local_maxima.T)] = True
    return mask

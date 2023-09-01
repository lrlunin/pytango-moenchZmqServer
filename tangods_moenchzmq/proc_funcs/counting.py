import numpy as np
from numba import njit

# from enum import IntEnum
# original code in pure python, to slow to use -> see the @njit version below
# class eventType(IntEnum):
#     NEIGHBOUR = 1
#     PHOTON = 2
#     PHOTON_MAX = 3
#     NEG_PEDESTAL = 4

# class quadrant(IntEnum):
#     TOP_LEFT = 0
#     TOP_RIGHT = 1
#     BOTTOM_LEFT = 2
#     BOTTOM_RIGHT = 3
#     UNDEFINED_QUADRANT = -1


# def getClustersSLS(frame, nSigma=3, rms=20, clusterSize=3):
#     cluster_map = np.zeros_like(frame, dtype=float)
#     for iy, ix in np.ndindex(frame.shape):
#         max_value = tl = tr = bl = br = tot = quad = quadTot = 0
"""
consedring two sizes of clusters (one "big" 3x3 cluster and 4 "mini" 2x2 sub-clusters)
we need to estimate the RMS of the its sums.

Since for the RMS of the sum (\sigma_{sum}) for normal distribution holds:
\sigma_{sum}^2 = \sum_{i = 1}^N \sigma_i^2 , where \sigma_i - RMS of the each pixel and N - number of pixels.

Assuming that the value distribution of each empty pixel is the same we are able to reduce the \sigma_i to
\sigma_{noise}, which is not index dependet.

Then the upper formula can be simplified to:
\sigma_{sum}^2 = \sum_{i = 1}^N \sigma_{noise}^2 = \sigma_{noise}^2 \cdot N
Therefore:
\sigma_{sum} = \sqrt{\sigma_{noise}^2 \cdot N} = \sqrt{N}\sigma_{noise}

In the case of quadratic clusters (sometimes clusters may be square but not quadratic):
N_cluster = clusterSize*clusterSize => \sqrt{N_cluster} = clusterSize

For subcluster (which takes a quarter of the "big" cluster) in general case:
N_sublcuster = ((clusterSize + 1) / 2) * ((clusterSize + 1) / 2) => \sqrt{N_subcluster} = (clusterSize + 1) / 2
Since the clustersize is an odd number i.e. 3 and a sub-cluster is not exactly a half (it has size 2 and not 1.5
we need to add 1 before division) 
"""
#         c2 = (clusterSize + 1) / 2
#         c3 = clusterSize
#         ee = None
#         for ir in range(-clusterSize // 2, clusterSize // 2 + 1):
#             for ic in range(-clusterSize // 2, clusterSize // 2 + 1):
#                 if (
#                     (iy + ir) >= 0
#                     and (iy + ir) < frame.shape[0]
#                     and (ix + ic) >= 0
#                     and (ix + ic) < frame.shape[1]
#                 ):
#                     v = frame[iy + ir, ix + ic]
#                     tot += v
#                     if ir <= 0 and ic <= 0:
#                         bl += v
#                     if ir <= 0 and ic >= 0:
#                         br += v
#                     if ir >= 0 and ic <= 0:
#                         tl += v
#                     if ir >= 0 and ic >= 0:
#                         tr += v
#                     if v > max_value:
#                         max_value = v
#             if frame[iy, ix] < -nSigma * rms:
#                 ee = eventType.NEG_PEDESTAL
#                 pass
#             if max_value > nSigma * rms:
#                 ee = eventType.PHOTON
#                 if frame[iy, ix] < max_value:
#                     continue
#             elif tot > c3 * nSigma * rms:
#                 ee = eventType.PHOTON
#             else:
#                 quad = quadrant.BOTTOM_RIGHT
#                 quadTot = br
#                 if bl >= quadTot:
#                     quad = quadrant.BOTTOM_LEFT
#                     quadTot = bl
#                 if tl >= quadTot:
#                     quad = quadrant.TOP_LEFT
#                     quadTot = tl
#                 if tr >= quadTot:
#                     quad = quadrant.TOP_RIGHT
#                     quadTot = tr
#                 if quadTot > c2 * nSigma * rms:
#                     ee = eventType.PHOTON
#             if ee == eventType.PHOTON and frame[iy, ix] == max_value:
#                 ee == eventType.PHOTON_MAX
#                 cluster_map[iy, ix] = 1
#     return cluster_map


@njit("i1[:,:](f8[:,:], f8)")
def getClustersSLS(frame, cut_off_adu):
    clusterSize = 3
    cluster_map = np.zeros((400, 400), dtype=np.int8)
    c2 = (clusterSize + 1) / 2
    c3 = clusterSize
    for iy in range(400):
        for ix in range(400):
            max_value = tl = tr = bl = br = tot = 0
            # 0 - no photon, 1- photon,  2 - photon_max
            ee = 0
            for ir in range(-clusterSize // 2, clusterSize // 2 + 1):
                for ic in range(-clusterSize // 2, clusterSize // 2 + 1):
                    if (
                        (iy + ir) >= 0
                        and (iy + ir) < frame.shape[0]
                        and (ix + ic) >= 0
                        and (ix + ic) < frame.shape[1]
                    ):
                        v = frame[iy + ir, ix + ic]
                        # consider non-negative values only
                        v = max(v, 0)
                        tot += v
                        if ir <= 0 and ic <= 0:
                            bl += v
                        if ir <= 0 and ic >= 0:
                            br += v
                        if ir >= 0 and ic <= 0:
                            tl += v
                        if ir >= 0 and ic >= 0:
                            tr += v
                        if v > max_value:
                            max_value = v
                if max_value > cut_off_adu:
                    ee = 1
                    if frame[iy, ix] < max_value:
                        continue
                elif tot > c3 * cut_off_adu:
                    ee = 1
                elif max(bl, br, tl, tr) > c2 * cut_off_adu:
                    ee = 1
                if ee == 1 and frame[iy, ix] == max_value:
                    ee == 2
                    cluster_map[iy, ix] = 1
    return cluster_map


@njit("u1[:,:](f8[:,:], f8[:,:], f8)")
def classifyPixel(frame, std, nsigma):
    clusterSize = 3
    class_mask = np.zeros((400, 400), dtype=np.uint8)
    c2 = np.sqrt((clusterSize + 1) // 2 * (clusterSize + 1) // 2)
    c3 = np.sqrt(clusterSize * clusterSize)
    for iy in range(400):
        for ix in range(400):
            rms = std[iy, ix]
            max_value = 0
            tl = 0
            tr = 0
            bl = 0
            br = 0
            tot = 0
            v = 0
            # ee == 0 - no photon (pedestal), 1 - photon,  2 - photon_max, 3 - negative pedestal
            ee = 0
            for ir in range(-clusterSize // 2, clusterSize // 2 + 1):
                for ic in range(-clusterSize // 2, clusterSize // 2 + 1):
                    if (
                        (iy + ir) >= 0
                        and (iy + ir) < frame.shape[0]
                        and (ix + ic) >= 0
                        and (ix + ic) < frame.shape[1]
                    ):
                        v = frame[iy + ir, ix + ic]
                        tot += v
                        if ir <= 0 and ic <= 0:
                            bl += v
                        if ir <= 0 and ic >= 0:
                            br += v
                        if ir >= 0 and ic <= 0:
                            tl += v
                        if ir >= 0 and ic >= 0:
                            tr += v
                        if v > max_value:
                            max_value = v
            if frame[iy, ix] < -nsigma * rms:
                ee = 3
                class_mask[iy, ix] = ee
                continue
            if max_value > nsigma * rms:
                ee = 1
                class_mask[iy, ix] = ee
                if frame[iy, ix] < max_value:
                    continue
            elif tot > c3 * nsigma * rms:
                ee = 1
                class_mask[iy, ix] = ee
            elif max(bl, br, tl, tr) > c2 * nsigma * rms:
                ee = 1
                class_mask[iy, ix] = ee
            if ee == 1 and frame[iy, ix] == max_value:
                ee = 2
                class_mask[iy, ix] = ee
    return class_mask


# there is possibility to run the same code on the gpu, not tested
# might be even slower due to the CPU <-> GPU data transport latency
# @cuda.jit("void(f8[:,:], i1[:,:], i1, i1, i1)")
# def getClustersCuda(frame, cluster_map, nSigma=3, rms=20, clusterSize=3):
#     for iy in range(0, 400):
#         for ix in range(0, 400):
#             max_value = tl = tr = bl = br = tot = quad = quadTot = 0
#             c2 = (clusterSize + 1) / 2
#             c3 = clusterSize
#             ee = 0
#             for ir in range(-clusterSize // 2, clusterSize // 2 + 1):
#                 for ic in range(-clusterSize // 2, clusterSize // 2 + 1):
#                     if (
#                         (iy + ir) >= 0
#                         and (iy + ir) < frame.shape[0]
#                         and (ix + ic) >= 0
#                         and (ix + ic) < frame.shape[1]
#                     ):
#                         v = frame[iy + ir, ix + ic]
#                         tot += v
#                         if ir <= 0 and ic <= 0:
#                             bl += v
#                         if ir <= 0 and ic >= 0:
#                             br += v
#                         if ir >= 0 and ic <= 0:
#                             tl += v
#                         if ir >= 0 and ic >= 0:
#                             tr += v
#                         if v > max_value:
#                             max_value = v
#                 if frame[iy, ix] < -nSigma * rms:
#                     ee = 4
#                     pass
#                 if max_value > nSigma * rms:
#                     ee = 2
#                     if frame[iy, ix] < max_value:
#                         continue
#                 elif tot > c3 * nSigma * rms:
#                     ee = 2
#                 else:
#                     # quad = quadrant.BOTTOM_RIGHT
#                     quadTot = br
#                     if bl >= quadTot:
#                         # quad = quadrant.BOTTOM_LEFT
#                         quadTot = bl
#                     if tl >= quadTot:
#                         # quad = quadrant.TOP_LEFT
#                         quadTot = tl
#                     if tr >= quadTot:
#                         # quad = quadrant.TOP_RIGHT
#                         quadTot = tr
#                     if quadTot > c2 * nSigma * rms:
#                         ee = 2
#                 if ee == 2 and frame[iy, ix] == max_value:
#                     ee == 3
#                     cluster_map[iy, ix] = 1  #  return cluster_map

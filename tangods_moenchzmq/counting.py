import numpy as np
from enum import IntEnum
from numba import njit, cuda


class eventType(IntEnum):
    NEIGHBOUR = 1
    PHOTON = 2
    PHOTON_MAX = 3
    NEG_PEDESTAL = 4


class quadrant(IntEnum):
    TOP_LEFT = 0
    TOP_RIGHT = 1
    BOTTOM_LEFT = 2
    BOTTOM_RIGHT = 3
    UNDEFINED_QUADRANT = -1


def getClusters(frame, nSigma=3, rms=20, clusterSize=3):
    cluster_map = np.zeros_like(frame, dtype=float)
    for iy, ix in np.ndindex(frame.shape):
        max_value = tl = tr = bl = br = tot = quad = quadTot = 0
        c2 = (clusterSize + 1) / 2
        c3 = clusterSize
        ee = None
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
            if frame[iy, ix] < -nSigma * rms:
                ee = eventType.NEG_PEDESTAL
                pass
            if max_value > nSigma * rms:
                ee = eventType.PHOTON
                if frame[iy, ix] < max_value:
                    continue
            elif tot > c3 * nSigma * rms:
                ee = eventType.PHOTON
            else:
                quad = quadrant.BOTTOM_RIGHT
                quadTot = br
                if bl >= quadTot:
                    quad = quadrant.BOTTOM_LEFT
                    quadTot = bl
                if tl >= quadTot:
                    quad = quadrant.TOP_LEFT
                    quadTot = tl
                if tr >= quadTot:
                    quad = quadrant.TOP_RIGHT
                    quadTot = tr
                if quadTot > c2 * nSigma * rms:
                    ee = eventType.PHOTON
            if ee == eventType.PHOTON and frame[iy, ix] == max_value:
                ee == eventType.PHOTON_MAX
                cluster_map[iy, ix] = 1
    return cluster_map


@njit("i1[:,:](f8[:,:], i1[:,:], i1, i1, i1)")
def getClustersJit(frame, cluster_map, nSigma=3, rms=20, clusterSize=3):
    # cluster_map = np.zeros([400, 400], dtype=np.int8)
    for iy, ix in np.ndindex(frame.shape):
        max_value = tl = tr = bl = br = tot = quad = quadTot = 0
        c2 = (clusterSize + 1) / 2
        c3 = clusterSize
        ee = ""
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
            if frame[iy, ix] < -nSigma * rms:
                ee = "neg"
                pass
            if max_value > nSigma * rms:
                ee = "photon"
                if frame[iy, ix] < max_value:
                    continue
            elif tot > c3 * nSigma * rms:
                ee = "photon"
            else:
                # quad = quadrant.BOTTOM_RIGHT
                quadTot = br
                if bl >= quadTot:
                    # quad = quadrant.BOTTOM_LEFT
                    quadTot = bl
                if tl >= quadTot:
                    # quad = quadrant.TOP_LEFT
                    quadTot = tl
                if tr >= quadTot:
                    # quad = quadrant.TOP_RIGHT
                    quadTot = tr
                if quadTot > c2 * nSigma * rms:
                    ee = "photon"
            if ee == "photon" and frame[iy, ix] == max_value:
                ee == "photon_max"
                cluster_map[iy, ix] = 1
    return cluster_map


@cuda.jit("void(f8[:,:], i1[:,:], i1, i1, i1)")
def getClustersCuda(frame, cluster_map, nSigma=3, rms=20, clusterSize=3):
    # cluster_map = np.zeros([400, 400], dtype=np.int8)
    for iy in range(0, 400):
        for ix in range(0, 400):
            max_value = tl = tr = bl = br = tot = quad = quadTot = 0
            c2 = (clusterSize + 1) / 2
            c3 = clusterSize
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
                if frame[iy, ix] < -nSigma * rms:
                    ee = 4
                    pass
                if max_value > nSigma * rms:
                    ee = 2
                    if frame[iy, ix] < max_value:
                        continue
                elif tot > c3 * nSigma * rms:
                    ee = 2
                else:
                    # quad = quadrant.BOTTOM_RIGHT
                    quadTot = br
                    if bl >= quadTot:
                        # quad = quadrant.BOTTOM_LEFT
                        quadTot = bl
                    if tl >= quadTot:
                        # quad = quadrant.TOP_LEFT
                        quadTot = tl
                    if tr >= quadTot:
                        # quad = quadrant.TOP_RIGHT
                        quadTot = tr
                    if quadTot > c2 * nSigma * rms:
                        ee = 2
                if ee == 2 and frame[iy, ix] == max_value:
                    ee == 3
                    cluster_map[iy, ix] = 1  #  return cluster_map

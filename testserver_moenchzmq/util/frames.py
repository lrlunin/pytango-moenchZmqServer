import numpy as np
from PIL import Image, ImageDraw, ImageFont
from importlib.resources import files


class Frame:
    def __init__(self, offset, noise_sigma):
        self._offset = offset
        self._noise_sigma = noise_sigma
        self._frame = np.random.normal(
            loc=offset, scale=noise_sigma, size=(400, 400)
        ).astype(np.uint16)

    def get_frame(self):
        return self._frame


class PedestalFrame(Frame):
    def __init__(self, offset, noise_sigma):
        super().__init__(offset, noise_sigma)


class SimulationFrame(Frame):
    def __init__(self, offset, noise_sigma, photons, photon_value=110):
        super().__init__(offset, noise_sigma)
        self._photons = photons
        self._photon_value = photon_value
        ys, xs = np.random.randint(0, 400, size=(2, photons))
        overlay = np.zeros((400, 400), dtype=np.uint16)
        overlay[ys, xs] = photon_value
        self._frame += overlay


class DigitFrame(Frame):
    def __init__(self, offset, noise_sigma, frame_number):
        super().__init__(offset, noise_sigma)
        self._frame_number = frame_number
        image = Image.fromarray(np.zeros((400, 400), dtype=np.uint16))
        draw = ImageDraw.Draw(image)
        x = frame_number // 15
        y = frame_number % 15
        draw.text(
            (y * 25, x * 25), str(frame_number), font=FrameUtils.roboto_font, fill=1
        )
        self._frame += np.array(image)


class FrameUtils:
    roboto_font_path = str(
        files("testserver_moenchzmq.util").joinpath("RobotoMono-Regular.ttf")
    )
    roboto_font = ImageFont.truetype(roboto_font_path, size=12)

    reorder_table = np.load(
        files("tangods_moenchzmq.reorder_tables").joinpath("moench03.npy")
    )
    inverse_table = np.argsort(np.ravel(reorder_table))

    def inverse_reorder(twod_array):
        return np.ravel(twod_array)[FrameUtils.inverse_table]

from os import path
from PIL import Image
import numpy as np
from datetime import datetime
import sys
from cairosvg import svg2png
import io

dir = path.dirname(__file__)

time = datetime.now()
save_folder = "default_images"
modes = ["ANALOG", "THRESHOLD", "COUNTING"]
pump_states = ["PUMPED", "UNPUMPED"]


today_formatted = time.strftime("%d/%m/%Y")
version = open("VERSION", encoding="utf-8").read()

# since the last update the inlined images in svg are not working anymore
# for the proper work of the preview the Roboto font should be installed on the system
# https://fonts.google.com/specimen/Roboto
# otherwise the preview will be generated with the default font
template = open(path.join(dir, "preview_template.svg"), "r", encoding="utf-8").read()

for mode in modes:
    for pump_state in pump_states:
        svg_formatted = template.format(
            date=today_formatted,
            version=version,
            processing_mode=mode,
            pump_state=pump_state,
        )
        png_bytes = svg2png(
            bytestring=svg_formatted,
            output_width=400,
            output_height=400,
        )
        # svg2png(
        #     bytestring=svg_formatted,
        #     output_width=400,
        #     output_height=400,
        #     write_to=f"{mode}_{pump_state}.png",
        # )
        pil_image = Image.open(io.BytesIO(png_bytes)).convert("L")
        numpy_array = np.array(pil_image)
        filename = path.join(save_folder, f"{mode.lower()}_{pump_state.lower()}")
        np.save(filename, numpy_array)

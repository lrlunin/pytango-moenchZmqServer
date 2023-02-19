from setuptools import setup

version = open("VERSION", encoding="utf-8").read()

setup(
    name="moenchzmqtangods",
    version=version,
    description="processing ZMQ server for a moench detector with tango DeviceServer",
    author="Leonid Lunin",
    author_email="lunin.leonid@gmail.com",
    python_requires=">=3.10",
    entry_points={"console_scripts": ["MoenchZmqServer = moenchzmqtangods:main"]},
    license="MIT",
    data_files=[
        ("default_images", ["default_images/*.npy"]),
        ("reorder_tables", ["reorder_tables/*.npy"]),
    ],
    url="https://github.com/lrlunin/pytango-moenchZmqServer",
    keywords=[
        "tango device",
        "tango",
        "pytango",
        "moench",
    ],
)

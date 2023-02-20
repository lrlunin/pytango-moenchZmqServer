from setuptools import setup
from glob import glob

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
    packages=["moenchzmqtangods"],
    package_data={"moenchzmqtangods": ["VERSION"]},
    data_files=[
        (
            "default_images",
            glob("default_images/*.npy"),
        ),
        ("reorder_tables", glob("reorder_tables/*.npy")),
        ("", ["VERSION"]),
    ],
    url="https://github.com/lrlunin/pytango-moenchZmqServer",
    keywords=[
        "tango device",
        "tango",
        "pytango",
        "moench",
    ],
)

from setuptools import setup
from glob import glob

version = open("VERSION", encoding="utf-8").read()

setup(
    name="tangods_moenchzmq",
    version=version,
    description="processing ZMQ server for a moench detector with tango DeviceServer",
    author="Leonid Lunin",
    author_email="lunin.leonid@gmail.com",
    python_requires=">=3.10",
    entry_points={"console_scripts": ["MoenchZmqServer = tangods_moenchzmq:main"]},
    license="MIT",
    packages=["tangods_moenchzmq"],
    # for future pip packaging
    # install_requires=[
    #     "pytango>=9.3.6",
    #     "nump>=1.24",
    #     "pyzmq>=23.2",
    #     "Pillow>=9.3",
    #     "numba>=0.57",
    # ],
    package_data={"tangods_moenchzmq": ["VERSION"]},
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

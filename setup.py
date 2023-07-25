from setuptools import setup

setup(
    name="ad-index",
    packages=["ad_index"],
    install_requires=[
        "selenium==4.10",
        "aiosqlite==0.19",
    ],
    author="Alex Nichol",
)

from setuptools import setup

setup(
    name="ad-index",
    packages=["ad_index"],
    install_requires=[
        "Pillow==9.0",
        "aiohttp==3.8",
        "aiosqlite==0.19",
        "cryptography==3.4",
        "jsonschema==4.17",
        "py-vapid==1.9",
        "pywebpush==1.14",
        "selenium==4.10",
    ],
    author="Alex Nichol",
)

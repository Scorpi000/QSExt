# -*- coding: utf-8 -*-
import setuptools
import os

with open("README.rst", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="QSExt",
    version="1.0.0",
    author="scorpi000",
    author_email="scorpi000@sina.cn",
    maintainer="scorpi000",
    maintainer_email="scorpi000@sina.cn",
    description="Quant Studio Extensions",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/Scorpi000/QuantStudio/",
    license="GPLv3",
    platforms=["Windows"],
    python_requires=">=3.5",
    scripts=[],
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        'Topic :: Office/Business :: Financial :: Investment'
    ],
    install_requires=[
        "QuantStudio",
    ],
    package_data={"QuantStudio": ["Resource/*"]}
)
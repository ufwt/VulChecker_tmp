#!/usr/bin/env python

from Cython.Build import cythonize
from setuptools import Extension, setup

setup(
    ext_modules=cythonize(
        [
            Extension("vulchecker._features", ["src/vulchecker/_features.pyx"]),
            Extension("vulchecker._graphs", ["src/vulchecker/_graphs.pyx"]),
        ]
    )
)

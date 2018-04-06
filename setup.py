#!/usr/bin/env python
"""Setuptools params."""

from setuptools import setup, find_packages, Extension

VERSION = '0.2.1'

modname = distname = 'stroboscope'

setup(
    name=distname,
    version=VERSION,
    description='Code and algorithms to run a stroboscope collector',
    author='Olivier Tilmans',
    author_email='olivier.tilmans@uclouvain.be',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Programming Language :: Python",
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Topic :: System :: Networking", ],
    keywords='networking monitoring traffic mirroring',
    license='GPLv2',
    install_requires=[
        'setuptools',
        'networkx==1.11',
        'paramiko',
        'ipaddress',
        'py-radix',
        'gurobipy>=7',
        'TatSu'],
    tests_require=['pytest>=2.10'],
    setup_requires=['pytest-runner'],
    ext_modules=[Extension('stroboscope._dissect', ['stroboscope/_dissect.c']),
                ],
    scripts=['bin/stroboscope-collector', 'bin/stroboscope-linux-backend'],
)

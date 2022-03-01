"""setup.py file for txwebutils"""

from setuptools import setup


setup(
    name="txwebutils",
    version="0.0.1",
    author="bennr01",
    author_email="benjamin99.vogt@web.de",
    description="Utilities for twisted web",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="twisted web utils unicode csauth xsauth",
    url="https://github.com/bennr01/txwebutils/",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Topic :: Internet :: WWW/HTTP",
        "Development Status :: 3 - Alpha",
        "Framework :: Twisted",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        ],
    packages=[
        "txwebutils",
        "txwebutils.csauth",
        "txwebutils.tests",
        ],
    install_requires=[
        "six",
        "Twisted",
        "zope.interface",
        "treq ~= 22.1.0",
        "expiringdict",
        ],
    )

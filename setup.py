import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="CRESTHH", # Replace with your own username
    version="0.0.1",
    author="Allen Zhi Li",
    author_email="li1995@ou.edu",
    description="A hydrologic and hydrodynamic coupling modeling framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/chrimerss/CRESTHH",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='==2.7',
)
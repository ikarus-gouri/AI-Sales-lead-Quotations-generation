"""Setup file for the package."""

from setuptools import setup, find_packages

setup(
    name="theraluxe-scraper",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "google-generativeai>=0.3.0",
    ],
    entry_points={
        'console_scripts': [
            'theraluxe-scraper=src.main:main',
        ],
    },
    author="Your Name",
    description="A modular web scraper for Theraluxe product catalog",
    python_requires='>=3.7',
)
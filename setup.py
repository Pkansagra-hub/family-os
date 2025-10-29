from setuptools import setup, find_packages

setup(
    name="familyos-k1-bridge",
    version="0.1.0",
    packages=find_packages(include=['k1*']),  # Only include k1 package
    install_requires=[
        'aiohttp>=3.9.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.21.0',
            'pytest-cov>=4.0.0',
            'black>=24.0.0',
            'isort>=5.12.0',
            'mypy>=1.8.0',
        ],
    },
    python_requires='>=3.10',
)

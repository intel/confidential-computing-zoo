"""
Setup script
"""
import io
from setuptools import setup


def load_readme():
    """
    Load content from README.md
    """
    with io.open('README.md', 'rt', encoding='utf8') as fobj:
        readme = fobj.read()
    return readme


def load_requirements():
    """
    Load content from requirements.txt
    """
    with open('requirements.txt', encoding='utf-8') as fobj:
        return fobj.read().splitlines()


setup(
    name='pytdxmeasure',
    version='0.0.7',
    packages=['pytdxmeasure'],
    package_data={
        '': ['tdx_eventlogs', 'tdx_tdreport', 'tdx_verify_rtmr', 'tdx_extend_rtmr']
    },
    include_package_data=True,
    python_requires='>=3.6.8',
    license='Apache License 2.0',
    scripts=['tdx_eventlogs', 'tdx_tdreport', 'tdx_verify_rtmr', 'tdx_extend_rtmr'],
    long_description=load_readme(),
    long_description_content_type='text/markdown',
    install_requires=load_requirements()
)

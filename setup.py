#!/usr/bin/env python3
from setuptools import setup, Command

import os
import sys
from shutil import rmtree
import httpx_html


here = os.path.abspath(os.path.dirname(__file__))

# Note: To use the 'upload' functionality of this file, you must:
#   $ pip install twine


class UploadCommand(Command):
    """Support setup.py upload."""

    description = 'Build and publish the package.'
    user_options = []

    @staticmethod
    def status(string):
        """Prints things in bold."""
        print(f'\033[1m{string}\033[0m')

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            self.status('Removing previous builds…')
            rmtree(os.path.join(here, 'dist'))
        except OSError:
            pass

        self.status('Building Source and Wheel distribution…')
        os.system(f'{sys.executable} setup.py sdist bdist_wheel')

        self.status('Uploading the package to PyPi via Twine…')
        os.system('twine upload dist/*')

        self.status('Publishing git tags…')
        os.system(f'git tag v{httpx_html.__version__}')
        os.system('git push --tags')

        sys.exit()


if __name__ == '__main__':
    setup()

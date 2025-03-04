#!/usr/bin/env python3
from setuptools import setup, Command as _Command
from pathlib import Path
from shutil import rmtree
import os
import sys

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE / 'src'))

import httpx_html  # noqa: E402


# Note: To use the 'upload' functionality of this file, you must:
#   $ pip install twine

def print_bold(string):
    '''Prints things in bold.
    '''
    print(f'\033[1m{string}\033[0m', flush=True)


class Command(_Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass


class UploadCommand(Command):

    description = 'Build and publish the package.'

    def run(self):
        try:
            print_bold('Removing previous builds…')
            rmtree(os.path.join(str(HERE), 'dist'))
        except OSError:
            pass

        print_bold('Building Source and Wheel distribution…')
        os.system(f'{sys.executable} setup.py sdist bdist_wheel')

        print_bold('Uploading the package to PyPi via Twine…')
        os.system('twine upload dist/*')

        print_bold('Publishing git tags…')
        os.system(f'git tag v{httpx_html.__version__}')
        os.system('git push --tags')

        sys.exit()


class MakeDocsCommand(Command):

    description = 'Make documentation.'

    def run(self):
        print_bold('Making documentation...')
        os.chdir(str(HERE / 'docs'))
        os.system('make html')

        # print_bold('Staging changes...')
        # os.chdir(str(HERE / 'docs/build/html'))
        # os.system('git add --all')
        # os.system('git commit -m "docs: updates"')

        # print_bold('Publishing GH Pages')
        # os.system('git push origin gh-pages')

        sys.exit()


if __name__ == '__main__':
    setup()

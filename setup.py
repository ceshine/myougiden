#!/usr/bin/env python3
import subprocess
import os
from distutils.command.install import install
from distutils.core import setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as f:
      # hacky markdown to ResT
    longdesc=f.read().replace(":\n", "::\n")

setup(name='myougiden',
      version='0.1.1',
      description='Japanese/English command-line dictionary',
      long_description=longdesc,
      author='Leonardo Boiko',
      author_email='leoboiko@gmail.com',
      url='https://github.com/leoboiko/myougiden',
      py_modules=['myougiden'],
      scripts=['bin/myougiden', 'bin/updatedb-myougiden'],
      license='GPLv3',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: Education',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Science/Research',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Natural Language :: English',
          'Natural Language :: Japanese',
          'Operating System :: POSIX',
          'Programming Language :: Python :: 3',
          'Topic :: Education',
          'Topic :: Text Processing :: Linguistic',
          ]
     )


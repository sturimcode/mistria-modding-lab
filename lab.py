#!/usr/bin/env python3
"""Entry point. Run: python lab.py --help"""
import sys

if sys.version_info < (3, 11):
    sys.exit('This lab needs Python 3.11 or newer.')

from mistria_lab.cli import main

if __name__ == '__main__':
    sys.exit(main())

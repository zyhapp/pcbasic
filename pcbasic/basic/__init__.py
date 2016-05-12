"""
PC-BASIC - GW-BASIC/BASICA/Cartridge BASIC compatible interpreter

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

__version__ = b'16.05.dev0'

from .codepage import codepages
from .font import fonts
from .session import Session, launch_session
from .error import *
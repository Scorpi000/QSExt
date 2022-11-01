# -*- coding: utf-8 -*-
import os

__QS_MainPath__ = os.path.split(os.path.realpath(__file__))[0]
__QS_LibPath__ = __QS_MainPath__+os.sep+"Lib"
__QS_ConfigPath__ = os.path.expanduser("~")+os.sep+"QuantStudioConfig"
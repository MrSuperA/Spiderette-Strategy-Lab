import pathlib
p = pathlib.Path(r"D:/project/Spiderette Strategy Lab/tests/test_sync_docs.py")
NL = chr(10)
BS = chr(92)
Q = chr(34)
QQ = Q+Q
def q(s): return Q+s+Q
def bs(s): return BS+s
lines = []
a = lines.append
a(QQ+"sync_docs.py unit tests"+QQ)
a("")
a("from __future__ import annotations")
a("import json, sys")
a("from pathlib import Path")
a("import pytest")
a("")
a("sys.path.insert(0, str(Path(__file__).parent.parent / "+q("tools")+"))")
a("import sync_docs as sd")

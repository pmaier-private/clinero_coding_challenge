import sys
from types import SimpleNamespace

# Stub out pyodbc so tests run without a native ODBC driver installed.
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = SimpleNamespace(connect=lambda _cs: None)

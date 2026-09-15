import os
import sys

root = sys.argv[1]
d = os.path.join(root, "sftp-drop", "upload")
os.makedirs(d, exist_ok=True)

def rec(cust, name, date, amt, ccy, rt):
    return cust.ljust(10)[:10] + name.ljust(30)[:30] + date.ljust(8)[:8] + amt.ljust(12)[:12] + ccy.ljust(3)[:3] + rt.ljust(2)[:2]

lines = []
lines.append("HDR CUSTBILL EXTRACT NS=PROBE      FILE=001")
lines.append(rec("C000000001", "NORMAL CO", "20240101", "000000010000", "USD", "01"))          # baseline 100.00
lines.append(rec("C000000002", "PIPE|NAME CO", "20240101", "000000020000", "USD", "01"))       # embedded pipe
lines.append("C000000003SHORTLINE")                                                             # short line
lines.append(rec("C000000004", "LONG CO", "20240101", "000000040000", "USD", "01") + "XXTRAILINGJUNK")  # long line
lines.append(rec("          ", "NO CUST ID CO", "20240101", "000000050000", "USD", "01"))      # blank cust id
lines.append(rec("C000000006", "BAD AMT CO", "20240101", "ABCDEFGHIJKL", "USD", "01"))         # non-numeric amount
lines.append(rec("C000000007", "BAD DATE CO", "20259999", "000000070000", "USD", "01"))        # impossible date
lines.append(rec("C000000008", "NO DATE CO", "        ", "000000080000", "USD", "01"))         # blank date
lines.append(rec("C000000009", "RT03 CO", "20240101", "000000090000", "USD", "03"))            # unknown rec type
lines.append(rec("C000000010", "  LEADING SPACES CO", "20240101", "000000100000", "USD", "01"))# leading spaces in name
lines.append(rec("C000000011", "NEG CO", "20240101", "-00000110000", "USD", "01"))             # signed amount
lines.append(rec("C000000012", "ODD AMT CO", "20240101", "000000000001", "usd", "1 "))         # 0.01, lowercase ccy, rt "1 "
lines.append("")                                                                                # blank line
lines.append(rec("HDRFAKE001", "LOOKS LIKE A HEADER", "20240101", "000000130000", "USD", "01"))# starts with HDR
lines.append(rec("C000000014", "ACCENT \xe9 CO", "20240101", "000000140000", "USD", "01"))     # latin-1 accented byte
lines.append("TRL0000000015")
blob = "\n".join(lines) + "\n"
with open(os.path.join(d, "CUSTBILL_PROBE_001.dat"), "wb") as f:
    f.write(blob.encode("latin-1"))

# UTF-8 multibyte file
u = [rec("C000000020", "CAF\u00c9 UTF8 CO", "20240101", "000000200000", "USD", "01")]
with open(os.path.join(d, "CUSTBILL_PROBE_002.dat"), "wb") as f:
    f.write(("\n".join(u) + "\n").encode("utf-8"))

# CRLF file
c = [rec("C000000030", "CRLF CO", "20240101", "000000300000", "USD", "01")]
with open(os.path.join(d, "CUSTBILL_PROBE_003.dat"), "wb") as f:
    f.write(("\r\n".join(c) + "\r\n").encode("ascii"))

# empty file
open(os.path.join(d, "CUSTBILL_PROBE_004.dat"), "wb").close()
print("wrote probe files")

import re
import sys

for line in sys.stdin:
  line = line.strip()
  m = re.match('(.*)Total: (.+) OOV: (.+)', line)
  if m:
    print(m.groups()[1])
  else:
    sys.stderr.write("No match: %s\n"%line)

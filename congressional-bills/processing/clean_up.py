import re
import sys

seen = set()
for line in sys.stdin:
  congress, bid, body, topic, summary, longtitle, shorttitle = line.strip().split('\t')
  if longtitle.startswith("A bill entitled"):
    continue
  summary = re.sub('\d\d\d\d', 'YEAR', summary)
  longtitle = re.sub('\d\d\d\d', 'YEAR', longtitle)
  shorttitle = re.sub('\d\d\d\d', 'YEAR', shorttitle)
  if shorttitle not in seen:
    seen.add(shorttitle)
    print '\t'.join([congress, bid, body, topic, summary, longtitle, shorttitle])


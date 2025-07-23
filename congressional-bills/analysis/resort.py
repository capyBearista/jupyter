import sys

#topic	N	llen	slen	lttr	sttr	levenstein	jaccard
lines = []

idx = int(sys.argv[1])

for i,line in enumerate(sys.stdin):
  if i > 0:
    elems = line.strip().split('\t')
    if float(elems[1]) >= 50:
      lines.append(elems)
  else:
    print(line)

for l in sorted(lines, key=lambda e:float(e[idx]), reverse=True):
  print('\t'.join(l))

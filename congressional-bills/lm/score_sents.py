import sys

for line in sys.stdin:
  logprob, toks = line.strip().split('\t')
  logprob = float(logprob)
  toks = toks.split()
  print logprob/len(toks)

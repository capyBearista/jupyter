import sys

longs = {}
for line in open('../lm/official_titles/official_titles.query_output.3gm.logprob.normed.ided').readlines():
  bid, lp = line.strip().split('\t')
  longs[bid] = float(lp)

shorts = {}
for line in open('../lm/short_titles/short_titles.query_output.3gm.logprob.normed.ided').readlines():
  bid, lp = line.strip().split('\t')
  shorts[bid] = float(lp)

for i,line in enumerate(sys.stdin):
  congress, bid, body, topic, summary, longtitle, shorttitle = line.strip().split('\t')
  llp = longs[bid]
  slp = shorts[bid]
  diff = llp - slp
  print '%.04f\t%.02f\t%.02f\t%s\t%s\t%s'%(diff, llp, slp, topic, longtitle, shorttitle)

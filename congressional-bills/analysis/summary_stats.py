import sys
from nltk.metrics.distance import edit_distance, jaccard_distance

def pad(s, L=50):
  if len(s) < L:
    return s + ' '*(L-len(s))
  return s

s_logprobs = {}
for line in open('../lm/short_titles/short_titles.query_output.3gm.logprob.ided').readlines():
  bid, lp = line.strip().split('\t')
  s_logprobs[bid] = float(lp)

lengths = {}
ttrs = {}
probs = {}

for i,line in enumerate(sys.stdin):
  congress, bid, body, topic, summary, longtitle, shorttitle = line.strip().split('\t')
  if i % 1000 == 0:
    sys.stderr.write('%s\n'%shorttitle)

  if topic not in lengths:
    lengths[topic] = {'long': [], 'short': []}
    ttrs[topic] = {'long': [set(), 0.], 'short': [set(), 0.]} #types, tokens
    probs[topic] = [] 


  ltoks = longtitle.lower().strip().split()
  stoks = shorttitle.lower().strip().split()

  probs[topic].append(s_logprobs[bid])

  for toks, nm in [(ltoks, 'long'), (stoks, 'short')]:

    lengths[topic][nm].append(float(len(toks)))

    for w in toks:
      ttrs[topic][nm][0].add(w)
      ttrs[topic][nm][1] += 1

print('\t'.join([pad('topic'), 'N', 'llen', 'slen', 'lttr', 'sttr', 'sprob']))

for topic in sorted(lengths, key=lambda e: len(lengths[e]['long']), reverse=True):

  sprobs = probs[topic]

  llens = lengths[topic]['long']
  ltyp, ltok = ttrs[topic]['long']

  slens = lengths[topic]['short']
  styp, stok = ttrs[topic]['short']

  sprob = sum(sprobs)/len(sprobs)

  llen = sum(llens)/len(llens)
  lttr = len(ltyp)/ltok

  slen = sum(slens)/len(slens)
  sttr = len(styp)/stok
 
  print('%s\t%d\t%.01f\t%.01f\t%.04f\t%.04f\t%.04f'%(pad(topic), len(llens), llen, slen, lttr, sttr, sprob)) 

  

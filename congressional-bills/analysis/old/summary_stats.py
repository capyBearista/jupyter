import sys
from nltk.metrics.distance import edit_distance, jaccard_distance

def pad(s, L=50):
  if len(s) < L:
    return s + ' '*(L-len(s))
  return s

def custom_distance(toks1, toks2):

  toks1set = set(toks1)

  ds = []
  for tok in toks2:
    if tok in toks1set:
      ds.append(0.)
    else:
      d = float(sys.maxint)
      for w in toks1set:
        d = min(d, edit_distance(tok, w))
      ds.append(d)

  return sum(ds)/len(ds)

lengths = {}
ttrs = {}
dists = {}

for i,line in enumerate(sys.stdin):
  congress, bid, body, topic, summary, longtitle, shorttitle = line.strip().split('\t')
  if i % 1000 == 0:
    sys.stderr.write('%s\n'%shorttitle)

  if topic not in lengths:
    lengths[topic] = {'long': [], 'short': []}
    ttrs[topic] = {'long': [set(), 0.], 'short': [set(), 0.]} #types, tokens
    #dists[topic] = [[], []] #levenstein, jaccard
    dists[topic] = [] #levenstein, jaccard


  ltoks = longtitle.lower().strip().split()
  stoks = shorttitle.lower().strip().split()

  #dists[topic][0].append(edit_distance(longtitle.lower().strip(), shorttitle.lower().strip()))
  dists[topic].append(custom_distance(ltoks, stoks))
  #dists[topic][1].append(jaccard_distance(set(ltoks), set(stoks)))

  for toks, nm in [(ltoks, 'long'), (stoks, 'short')]:

    lengths[topic][nm].append(float(len(toks)))

    for w in toks:
      ttrs[topic][nm][0].add(w)
      ttrs[topic][nm][1] += 1

#print '\t'.join([pad('topic'), 'N', 'llen', 'slen', 'lttr', 'sttr', 'levenstein', 'jaccard'])
print '\t'.join([pad('topic'), 'N', 'llen', 'slen', 'lttr', 'sttr', 'dist'])

for topic in sorted(lengths, key=lambda e: len(lengths[e]['long']), reverse=True):

  #levs, jacs = dists[topic]
  levs = dists[topic]

  llens = lengths[topic]['long']
  ltyp, ltok = ttrs[topic]['long']

  slens = lengths[topic]['short']
  styp, stok = ttrs[topic]['short']

  lev = sum(levs)/len(levs)
  #jac = sum(jacs)/len(jacs)

  llen = sum(llens)/len(llens)
  lttr = len(ltyp)/ltok

  slen = sum(slens)/len(slens)
  sttr = len(styp)/stok
 
  #print '%s\t%d\t%.01f\t%.01f\t%.04f\t%.04f\t%.04f\t%.04f'%(pad(topic), len(llens), llen, slen, lttr, sttr, lev, jac) 
  print '%s\t%d\t%.01f\t%.01f\t%.04f\t%.04f\t%.04f'%(pad(topic), len(llens), llen, slen, lttr, sttr, lev) 

  

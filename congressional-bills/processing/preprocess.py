import sys
import json
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag

#82	None	134	hconres134-82	hconres	Certain Allottees on Crow Indian Reservation.	None

#n = float(sys.argv[1])
#lower = 1000 * n
#upper = 1000 * (n+1)

#sys.stderr.write("Processing %s\n"%n)

for i,line in enumerate(sys.stdin):
  if True: #i >= lower and i < upper:
    if i %1000 == 0:
      sys.stderr.write("Beginning batch %s\n"%i)
    sess, date, num, bid, btype, titles = line.strip().split('\t')
    titles = json.loads(titles)
    processed_titles = []
    for titleblob in titles:
      title = titleblob['title']
      typ = titleblob['type']
      toks = word_tokenize(title)
      postags = pos_tag(toks)
      lctoks = []
      tags = []
      for w,t in postags:
        lctoks.append(w.lower())
        tags.append(t)
      titleblob['title_lc'] = ' '.join(lctoks) 
      titleblob['title_pos'] = ' '.join(tags) 
      processed_titles.append(titleblob)
    print '\t'.join([sess, date, num, bid, btype, json.dumps(processed_titles)])
  

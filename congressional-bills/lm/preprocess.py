import re
import sys
from nltk.tokenize import sent_tokenize, word_tokenize

split_sentences = True if sys.argv[1] == 'True' else False

if split_sentences:
  for line in sys.stdin:
    for sent in sent_tokenize(line):
      toks = word_tokenize(sent)
      s = ' '.join(toks)
      s = re.sub('YEAR', '####', s)
      s = re.sub('\d', '#', s)
      print(s.lower())

else:
  for sent in sys.stdin:
    toks = word_tokenize(sent)
    s = ' '.join(toks)
    s = re.sub('YEAR', '####', s)
    s = re.sub('\d', '#', s)
    print(s.lower())

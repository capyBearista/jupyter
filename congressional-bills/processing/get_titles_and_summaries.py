import os
import sys
import pdb
import json

for _cong in range(93, 115):
  cong = '%s'%_cong
  if os.path.exists(cong) and os.path.isdir(cong):
    sys.stderr.write('%s\n'%cong)
    for bills in os.listdir(cong):
      for billtype in os.listdir('%s/%s'%(cong, bills)):
        for bill in os.listdir('%s/%s/%s'%(cong, bills, billtype)):
          data_path = '%s/%s/%s/%s/data.json'%(cong, bills, billtype, bill)
          if os.path.exists(data_path):
            data = json.loads(open(data_path).read())
            if 'summary' in data:
              bill_id = ('%s'%(data['bill_id'])).encode('ascii', 'ignore')
              bill_type = ('%s'%(data['bill_type'])).encode('ascii', 'ignore')
              introduced_at = ('%s'%(data['introduced_at'])).encode('ascii', 'ignore')
              number = ('%s'%(data['number'])).encode('ascii', 'ignore')
              congress = ('%s'%(data['congress'])).encode('ascii', 'ignore')
              titles = data['titles']
              title = None
              shorttitle = None
              for t in titles:
                if t['type'] == 'official':
                  title = t['title'].encode('ascii', 'ignore')
                if (t['type'] == 'short') or (t['type'] == 'popular'):
                  shorttitle = t['title'].encode('ascii', 'ignore')
              topic = data['subjects_top_term']
              if topic is None:
                topic = 'None'
              if data['summary'] is not None:
                summary = (' '.join(data['summary']['text'].split())).encode('ascii', 'ignore')
                try:
                  #print '\t'.join([congress, bill, bill_type, topic, title, summary, json.dumps(titles).encode('ascii', 'ignore')])
                  print '\t'.join([congress, bill, bill_type, topic, summary, title, shorttitle])
                except TypeError:
                   sys.stderr.write("ValueError: %s\n"%('\t'.join([bill])))
                   #pdb.set_trace()
            else:
              sys.stderr.write("No summary: %s\n"%('\t'.join([bill])))



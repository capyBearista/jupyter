import os
import sys
import json


for cong in os.listdir('.'):
  if os.path.isdir(cong):
    sys.stderr.write('%s\n'%cong)
    for bills in os.listdir(cong):
      for sess in os.listdir('%s/%s'%(cong, bills)):
        for bill in os.listdir('%s/%s/%s'%(cong, bills, sess)):
          data_path = '%s/%s/%s/%s/data.json'%(cong, bills, sess, bill)
          if os.path.exists(data_path):
            data = json.loads(open(data_path).read())
            bill_id = ('%s'%(data['bill_id'])).encode('ascii', 'ignore')
            bill_type = ('%s'%(data['bill_type'])).encode('ascii', 'ignore')
            introduced_at = ('%s'%(data['introduced_at'])).encode('ascii', 'ignore')
            number = ('%s'%(data['number'])).encode('ascii', 'ignore')
            congress = ('%s'%(data['congress'])).encode('ascii', 'ignore')
            titles = json.dumps(data['titles']).encode('ascii', 'ignore')
#            official_title = ('%s'%(data['official_title'])).encode('ascii', 'ignore')
#            if 'popular_title' in data: 
#              popular_title = ('%s'%(data['popular_title'])).encode('ascii', 'ignore')
#            else:
#              popular_title = 'NA'
#            print '\t'.join([congress, introduced_at, number, bill_id, bill_type, congress, official_title, popular_title])
            print '\t'.join([congress, introduced_at, number, bill_id, bill_type, titles])



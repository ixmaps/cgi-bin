#!/usr/bin/python

#FIXME  errors should never give a 2xx response

import pg
import time
import cgi
import cgitb; cgitb.enable()
from ixmaps import DBConnect

class TracerouteException(Exception):
    pass

def new_traceroute(conn, d):
    sub_time = "%04d-%02d-%02d %02d:%02d:%02d" % time.localtime()[:6]

    vstr="('%s', '%s', '%s', '%s', '%s', %d, %d, '%s', %d, '%s', %d)" % (sub_time, d['dest'], d['dest_ip'], \
        d['submitter'], d['zip_code'], d['privacy'], d['timeout'], d['protocol'], d['maxhops'], d['status'], d['attempts'])
    qstr = "insert into traceroute (sub_time, dest, dest_ip, submitter, zip_code, privacy, timeout, protocol, maxhops, status, attempts) values "+vstr
    conn.query(qstr)
#    except pg.ProgrammingError, e:
#        print str(e)
    qres = conn.query("select * from traceroute where sub_time='%s' and dest_ip='%s'" % (sub_time, d['dest_ip']))
    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise TracerouteException, "failed to determine an ID"
    return id

def ip_addr_present(conn, addr):
    qres = conn.query("select count(*) from ip_addr_info where ip_addr='%s'" % addr)
    return qres.dictresult()[0]['count'] == 1

def new_ip_addr(conn, addr):
    qres = conn.query("insert into ip_addr_info (ip_addr) values ('%s')" % addr)
    
def new_tr_item(conn, id, hop, attempt, d):
    (status, ip_addr, rtt_ms) = (d['status'], d['ip_addr'], d['rtt_ms'])
    if ip_addr:
        ipa_str = "'%s'" % ip_addr
        if not ip_addr_present(conn, ip_addr):
            new_ip_addr(conn, ip_addr)
    else:
        ipa_str = "NULL"
    vstr="(%d, %d, %d, '%s', %s, %d)" % (id, hop, attempt, status, ipa_str, rtt_ms)
    qstr = "insert into tr_item (traceroute_id, hop, attempt, status, ip_addr, rtt_ms) values "+vstr
    conn.query(qstr)

def get_tr_item_count(conn, id):
    qstr = "select count(*) from tr_item where traceroute_id=%d" % id
    qres = conn.query(qstr)
    ent = qres.dictresult()[0]
    return ent['count']
    
def sanitize_str(s):
    safe_chars = " !$*+,-./0123456789:=?ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
    try:
        return ''.join(filter(lambda x: x in safe_chars, [c for c in s]))
    except TypeError:
        return ''

def sanitize_traceroute(d):
    d['dest'] = sanitize_str(d['dest'])
    d['dest_ip'] = sanitize_str(d['dest_ip'])
    d['submitter'] = sanitize_str(d['submitter'])
    if len(d['submitter']) == 0:
        d['submitter'] = "not-specified"
    d['zip_code'] = sanitize_str(d['zip_code'])[:10]
    d['privacy'] = int(d['privacy'])
    d['timeout'] = int(d['timeout'])
    d['protocol'] = sanitize_str(d['protocol'])
    d['maxhops'] = int(d['maxhops'])
    d['status'] = sanitize_str(d['status'])
    d['attempts'] = int(d['attempts'])
    if not ( 1 <= d['attempts'] <= 10 ):
        return False
    if not ( 1 <= d['maxhops'] <= 255 ):
        return False
    return True

def sanitize_tr_item(d):
    #print d
    d['status'] = sanitize_str(d['status'])
    d['ip_addr'] = sanitize_str(d['ip_addr'])
    d['rtt_ms'] = int(d['rtt_ms'])
    return True

response_begin="""<html>
 <head>
  <title>Traceroute submission</title>
 <head>
 <body>
"""

response_end=""" </body>
</html>"""

print "Content-Type: text/html"
print 
print response_begin

form = cgi.FieldStorage()

traceroute={}
flds = ['dest', 'dest_ip', 'submitter',  'zip_code', 'privacy',  'timeout',   'protocol',  'maxhops', 'status', 'attempts']

for fld in flds:
    traceroute[fld] = form.getfirst(fld)

n_items = int(form.getfirst("n_items"))

conn = DBConnect.getConnection()

# ERROR messages given in standardized format
# ERROR(n): text
# where 300<=n<=345
if sanitize_traceroute(traceroute):
    id = new_traceroute(conn, traceroute)
    print traceroute
    print id
    try:
        for hop in range(1, 1+traceroute['maxhops']):
            for attempt in range(1, 1+traceroute['attempts']):
                suffix = "_%d_%d" % (hop, attempt)
                tr_item = {}
                tr_item['status'] = form["status"+suffix]
                tr_item['status'] = form.getfirst("status"+suffix)
                tr_item['ip_addr'] = form.getfirst("ip_addr"+suffix, '')
                tr_item['rtt_ms'] = form.getfirst("rtt_ms"+suffix, -1)
                print tr_item
                if sanitize_tr_item(tr_item):
                    new_tr_item(conn, id, hop, attempt, tr_item)
                else:
                    print "ERROR(301): sanitization of traceroute item failed"
    except KeyError:
        pass
    item_count = get_tr_item_count(conn, id)
    print item_count, n_items
    if item_count != n_items:
       print "ERROR(302): %d items declared != %d items in database" % (n_items, item_count)
       #FIXME delete traceroute!!
    print "new traceroute ID=%d" % id
else:
    print "sanitization of traceroute header failed"


print response_end

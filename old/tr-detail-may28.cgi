#!/usr/bin/python

#FIXME  errors should never give a 2xx response

import pg
import time
import cgi
import cgitb; cgitb.enable()
from ixmaps import DBConnect, sanitize_str

# persuant to OPEN DATA LICENSE (GeoLite Country and GeoLite City databases)
MAX_MIND_ATTRIBUTION="""
  <br/><br/>
This product includes GeoLite data created by MaxMind, available from
<a href="http://maxmind.com/">http://maxmind.com/</a>
"""

class TracerouteException(Exception):
    pass

def get_traceroute(conn, id):
    qres = conn.query("select * from traceroute where id=%d" % id)
    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise TracerouteException, "failed to find traceroute %d" % id
    return qres.dictresult()[0]

def get_traceroute_grp(conn, submitter, zip_code):
    qstr = "select * from traceroute where "
    if submitter:
        qstr += "submitter='%s'" % submitter
    else:
        qstr += "zip_code='%s'" % zip_code
    qres = conn.query(qstr)
    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise TracerouteException, "failed to find any traceroutes"
    return qres.dictresult()

def _get_traceroute_unique_fld(conn, qstr):
    qres = conn.query(qstr)
    return qres.dictresult()

def get_traceroute_submitters(conn):
    qstr = "select count(*), submitter from traceroute group by submitter order by submitter"
    return _get_traceroute_unique_fld(conn, qstr)

def get_traceroute_zip_codes(conn):
    qstr = "select count(*), zip_code from traceroute group by zip_code order by zip_code"
    return _get_traceroute_unique_fld(conn, qstr)

def show_traceroute_hdr(tr):
    if tr['dest'] == tr['dest_ip']:
        suffix = ""
    else:
        suffix = " [%s]" % tr['dest_ip']
    link = anchor_tr_kml(tr['id'], "GoogleEarth")
    return "id=<b>%6d</b> <b>%s</b> when=<b>%-16.16s</b>  from=<b>%s</b> to=<b>%s%s</b>" % \
           (tr['id'], link, tr['sub_time'], str(tr['zip_code']), tr['dest'], suffix)

def show_tr_group_hdr(tr_grp, submitter, zip_code):
    if submitter:
        whence = "user " + submitter
    else:
        whence = "location " + zip_code
    return "%d traceroutes submitted for %s" % (len(tr_grp), whence)

def get_tr_items(conn, id):
    qres = conn.query("select * from tr_item where traceroute_id=%d" % id)
    try:
        id = qres.dictresult()[0]['traceroute_id']
    except IndexError:
        raise TracerouteException, "failed to find traceroute items for %d" % id
    return qres.dictresult()

def get_ip_addr_info_geoloc(conn, latitude, longitude, radius):
    d_lat2 = 0.5 * radius;
    d_long2 = 0.5 * radius;
    qstr = "select * from ip_addr_info where %f<lat and lat<%f and %f<long and long<%f" % (
        latitude-d_lat2, latitude+d_lat2, longitude-d_long2, longitude+d_long2)
    qres = conn.query(qstr)
    return qres.dictresult()
    
def get_tr_items_by_ip_addr(conn, ip_addr):
    qres = conn.query("select * from tr_item where ip_addr=inet('%s')" % ip_addr)
    try:
        id = qres.dictresult()[0]['traceroute_id']
    except IndexError:
        raise TracerouteException, "failed to find traceroute items for %s" % ip_addr
    return qres.dictresult()


def get_tr_items_dim(da):
    """da is array of dicts, each dict representing a single traceroute probe"""
    nhops = nattempts = 0
    for d in da:
        if d['attempt'] > nattempts:
            nattempts = d['attempt']
        if d['hop'] > nhops:
            nhops = d['hop']
    return (nhops, nattempts)


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

def new_tr_item(conn, id, hop, attempt, d):
    (status, ip_addr, rtt_ms) = (d['status'], d['ip_addr'], d['rtt_ms'])
    if ip_addr:
        ipa_str = "'%s'" % ip_addr
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
    
def sanitize_traceroute(d):
    #FIXME protect against XSS attacks
    d['privacy'] = int(d['privacy'])
    d['timeout'] = int(d['timeout'])
    d['maxhops'] = int(d['maxhops'])
    d['attempts'] = int(d['attempts'])
    if not ( 1 <= d['attempts'] <= 10 ):
        return False
    if not ( 1 <= d['maxhops'] <= 255 ):
        return False
    return True

def sanitize_tr_item(d):
    #FIXME protect against XSS attacks
    d['rtt_ms'] = int(d['rtt_ms'])
    return True

def array_2d(rows, cols):
    a=[None]*rows
    for i in range(rows):
        a[i] = [None]*cols
    return a

def anchor_tr(id, text):
    return '<a href="tr-detail.cgi?traceroute_id=%d">%s</a>' % (id, text)

def anchor_tr_kml(id, text):
    return '<a href="ge-render.cgi?traceroute_id=%d">%s</a>' % (id, text)

def anchor_submitter(id):
    text = id
    if not text:
        text = " "
    text = sanitize_str(text)
    return '<a href="tr-detail.cgi?submitter=%s">%s</a>' % (id, text)

def anchor_zip_code(id):
    text = id
    if not text:
        text = " "
    text = sanitize_str(text)
    return '<a href="tr-detail.cgi?zip_code=%s">%s</a>' % (id, text)

def get_ip_addr_info(conn, addr):
    if addr:
        qres = conn.query("select * from ip_addr_info where ip_addr='%s'" % addr)
        d = qres.dictresult()[0]
        d['lat'] = str(d['lat'])
        d['long'] = str(d['long'])
        d['asnum'] = str(d['asnum'])
    else:
        d={'lat': '', 'hostname': '', 'ip_addr': None, 'long': '', 'asnum': ''}
    return d

def show_one_traceroute(conn, traceroute_id):
    print tr_response_begin
    try:
        tr_header = get_traceroute(conn, traceroute_id)
        print show_traceroute_hdr(tr_header)
        tr_body = get_tr_items(conn, traceroute_id)
        #print tr_body

        # allocate and fill the address and rtt tables
        (nhops, nattempts) = get_tr_items_dim(tr_body)   
        #print nhops, nattempts
        rtt = array_2d(nhops, nattempts)
        ipaddrs = array_2d(nhops, nattempts)
        for probe in tr_body:
            hop = probe['hop']-1
            attempt = probe['attempt']-1
            rtt[hop][attempt] = probe['rtt_ms']
            ipaddrs[hop][attempt] = probe['ip_addr']

        # display the table
        print '<table><tr><th>hop</th><th>IP Address</th><th colspan="%d">Round Trip Times</th>' % nattempts,
        print '<th>AS#</th><th>Latitude</th><th>Longitude</th><th>Hostname</th></tr>\n'
        for hop in range(nhops):
            print '<tr align="right"><td>%d</td>' % (hop+1),
            #print "%3d" % (hop+1),
            pr_addr = None
            mixed = ""
            for attempt in range(nattempts):
                this_ipaddr = ipaddrs[hop][attempt]
                if this_ipaddr:
                    if not pr_addr:
                        pr_addr = this_ipaddr
                    elif pr_addr != this_ipaddr:
                        mixed = "m"
            a_info = get_ip_addr_info(conn, pr_addr)
            if pr_addr:
                pr_addr = str(pr_addr)
            else:
                pr_addr = "NoResponse"
            print '<td align="left">%s</td>' % (pr_addr+mixed),
            for attempt in range(nattempts):
                #if ipaddrs[hop][attempt]:
                #    pr_addr = str(ipaddrs[hop][attempt])
                #else:
                #    pr_addr = "NoResponse"
                #print "    %-16.16s %4s" % (pr_addr, str(rtt[hop][attempt]))
                if rtt[hop][attempt] < 0:
                    s_rtt = '*'
                else:
                    s_rtt = str(rtt[hop][attempt])
                print '<td>%s</td>' % s_rtt,
            print '<td>%s</td><td>%s</td><td>%s</td><td>%s</td>' % \
                  (a_info['asnum'], a_info['lat'], a_info['long'], a_info['hostname'])
            print "</tr>"
        print "</table>"
	print MAX_MIND_ATTRIBUTION
    except TracerouteException:
        print tr_response_not_found

def show_grp_traceroutes(conn, submitter, zip_code):
    print grp_response_begin
    try:
        tr_grp = get_traceroute_grp(conn, submitter, zip_code)
        print show_tr_group_hdr(tr_grp, submitter, zip_code)
        if submitter:
            key = 'zip_code'
        else:
            key = 'submitter'
        print "<table>"
        print "<tr><th>id</th><th>date/time</th><th>%s</th><th>destination</th></tr>" % key
        for tr in tr_grp:
            #submitter = sanitize_str(tr['submitter'])
            #zip_code = sanitize_str(tr['zip_code'])
            key_val = sanitize_str(tr[key])
            dest = sanitize_str(tr['dest'])
            if dest == tr['dest_ip']:
                suffix = ""
            else:
                suffix = " [%s]" % tr['dest_ip']
            print "<tr><td>",
            print anchor_tr(tr['id'], str(tr['id'])),
            print "</td><td>%.16s</td><td>%s</td><td>%s%s</td></tr>" % (tr['sub_time'], key_val, dest, suffix)
            #print " %-16.16s %s %s  to  %s%s" % ( tr['sub_time'], submitter, zip_code, dest, suffix)
        print "</table>"
    except TracerouteException:
        print grp_response_not_found

response_begin="""<html>
 <head>
  <title>%s</title>
 <head>
 <body>
  <h2>%s</h2>
"""

tr_response_begin="""<html>
 <head>
  <title>Traceroute detail</title>
 <head>
 <body>
  <h2>Traceroute detail</h2>
"""

tr_response_not_found="""<p>No data found for that traceroute</p>"""

grp_response_begin="""<html>
 <head>
  <title>Traceroutes available</title>
 <head>
 <body>
  <h2>Available traceroutes</h2>
"""

grp_response_not_found="""<p>No traceroutes found</p>"""

response_end=""" </body>
</html>"""

print "Content-Type: text/html"
print 

form = cgi.FieldStorage()

try:
    traceroute_id = int(form.getfirst("traceroute_id"))
except TypeError:
    traceroute_id = 0

submitter = form.getfirst("submitter")

zip_code = form.getfirst("zip_code")

#print traceroute_id, submitter, zip_code

conn = DBConnect.getConnection()

if traceroute_id:
    show_one_traceroute(conn, traceroute_id)
elif submitter:
    show_grp_traceroutes(conn, submitter, '') 
elif zip_code:
    show_grp_traceroutes(conn, '', zip_code) 
elif form.getfirst("all_submitters"):
    print response_begin % ('submitters', 'submitters')
    sl = get_traceroute_submitters(conn)
    print """<p>To view this data graphically, you must have <a href="http://earth.google.com/download-earth.html">Google Earth</a> downloaded and installed :</p>
     <ol>
     <li>click on: any submitter name (eg Nancy).</li>
     <li>click on: any id number (eg 378   2009-11-01   16:31 M6J3N4  www.ciis.edu   [66.116.110.231])</li>
     <li>On the Traceroute Detail page - on the top line Google Earth is hyperlinked - select it and Google Earth will automatically launch the visualization</li></ol>"""

    print "<table><tr><th>count</th><th>submitter</th></tr>"
    for s in sl:
        print "<tr><td>%d</td>" % s['count'],
        print "<td>%s</td></tr>" % anchor_submitter(s['submitter'])
    print "</table>"
elif form.getfirst("all_zip_codes"):
    print response_begin % ('originating locations', 'originating locations')
    sl = get_traceroute_zip_codes(conn)
    print "<table><tr><th>count</th><th>zip/postal code</th></tr>"
    for s in sl:
        print "<tr><td>%d</td>" % s['count'],
        print "<td>%s</td></tr>" % anchor_zip_code(s['zip_code'])
    print "</table>"

print '<p>You can also look up traceroutes by <a href="tr-distance.cgi">geographic proximity</a> to a location.</p>'
print response_end
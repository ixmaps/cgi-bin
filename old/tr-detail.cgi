#!/usr/bin/python

#FIXME  errors should never give a 2xx response

import pg
import time
import cgi
import cgitb; cgitb.enable()
import ixmaps2_tmp
import sys
import math
from ixmaps import DBConnect, sanitize_str

# persuant to OPEN DATA LICENSE (GeoLite Country and GeoLite City databases)
MAX_MIND_ATTRIBUTION="""
  <br/>
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

    if submitter:
        criteria_type = "submitter"
        criteria = submitter
    else:
        criteria_type = "zip_code"
        criteria = zip_code

    # --- Get a list of traceroutes with their associated countries--
    #     including zero countries (takes some finagling...) ---
    qstr = """/** Select all traceroutes (and traits) for a particular sumbitter
    (or zip code), including traceroutes with zero countries **/ 
(
    /** Select all traceroutes, for a particular submitter (or zip code),
        without a single IP going through a known country **/
    select *, 'xx' as country_code from traceroute TR, traceroute_traits TRT 
    where
    (
        /** Select all traceroute-IDs, for a particular submitter/zip-code,
            without any known countries **/
        TR.id not in
        (
            /** Select all traceroute-IDs, for a particular submitter/zip-code,
                which go through known countries **/
            select TR.id from traceroute TR, traceroute_traits TRT, traceroute_countries TRC
            where
            (
                TR.id = TRT.id
                and TR.id = TRC.traceroute_id 
                and %s='%s'
            )
        )
        and TR.id = TRT.id
        and %s='%s'
    )
)
union
(
    /** Select all traceroutes, for a particular submitter/zip-code, and
        each country that it goes through **/
    select TR.*, TRT.*, TRC.country_code 
    from traceroute TR, traceroute_traits TRT, traceroute_countries TRC
    where
    (
        TR.id = TRT.id 
        and TR.id = TRC.traceroute_id 
        and %s='%s' 
    )
)
order by 1""" % (criteria_type, criteria, criteria_type, criteria,
                 criteria_type, criteria)

    # print "<pre>"
    # print (qstr), "\n"
    # print "</pre>"

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

    try:
        a_info = get_ip_addr_info(conn, tr['dest_ip'])
        dest_city = a_info['city'] + ' ' + a_info['state']
    except IndexError:
        dest_city = tr['dest']

    #yay for excessive pulling from the database! I'm ashamed of how ugly this is
    #temp_ip = conn.query("select traceroute_id from tr_item where hop=1 and attempt=1 and traceroute_id=%d" % id)
    #origin_city = conn.query("select mm_city from ip_addr_info where ip_addr='%s'" % temp_ip)
    link = anchor_tr_kml(tr['id'], "Open in GoogleEarth")
    if dest_city == tr['dest']:
        return "Traceroute id: <b>%6d</b>   &nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp<b>%s</b> <br/> origin: <b>%s</b>&nbsp&nbsp destination: <b>%s</b> %s <br/> submitter: %s &nbsp submitted: %-16.16s  " % \
        (tr['id'], link, tr['zip_code'], dest_city, suffix, tr['submitter'], tr['sub_time'])
    else:
        return "Traceroute id: <b>%6d</b>   &nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp<b>%s</b> <br/> origin: <b>%s</b>&nbsp&nbsp destination: <b>%s</b> (%s%s) <br/> submitter: %s &nbsp submitted: %-16.16s  " % \
        (tr['id'], link, tr['zip_code'], dest_city, tr['dest'], suffix, tr['submitter'], tr['sub_time'])
        

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
        d['hostname'] = str(d['hostname'])
        d['asnum'] = str(d['asnum'])
        d['city'] = str(d['mm_city'])
        d['state'] = str(d['mm_region'])
        d['certainty'] = str(d['gl_override'])
        qres = conn.query("select * from as_users where num='%s'" % d['asnum'])
        d2 = qres.dictresult()[0]
        d['ISP'] = str(d2['name'])
    else:
        d={'lat': '', 'hostname': '', 'ip_addr': None, 'long': '', 'asnum': '', 'city': 'unknown', 'name': '', 'ISP': '', 'state': '', 'certainty': ''}
    return d

def get_lowest_positive(number_list):
    x = sys.maxint;
    for item in number_list:
        if item < x and item > -1:
            x = item
    if x == sys.maxint:
        x = '*'
    return x

def get_min_latency(hop, rtt_array, nhop):
    x = 0
    mins_list = []
    hop = int(hop)
    nhop = int(nhop)
    while x < nhop:
        mins_list.append(get_lowest_positive(rtt_array[x]))
        x=x+1
    x = len(mins_list)
    while x > hop:
        if (mins_list[x-2] > mins_list[x-1]) and (mins_list[x-1] != '*'):
            mins_list[x-2] = mins_list[x-1]
        x=x-1
    return mins_list[hop]

# not being used currently
def get_certainty_value(gl_ov):
    certainty_value = ''
    if int(gl_ov) >= 5 and int(gl_ov) < 1000:
        certainty_value = 'high'
    elif int(gl_ov) == 2 or int(gl_ov) == 3:
        certainty_value = 'medium'
    elif int(gl_ov) == 1:
        certainty_value = 'low'
    else:
        certainty_value = 'unknown'
    return certainty_value


def show_one_traceroute(conn, traceroute_id):
    print tr_response_begin
    try:
        tr_header = get_traceroute(conn, traceroute_id)
        print show_traceroute_hdr(tr_header)
        tr_body = get_tr_items(conn, traceroute_id)
        # print "\ntr_body:", tr_body , "\n\n"

        # allocate and fill the address and rtt tables
        (nhops, nattempts) = get_tr_items_dim(tr_body)   
        # print "\n(nhops, nattempts):", nhops, nattempts

        rtt = array_2d(nhops, nattempts)
        ipaddrs = array_2d(nhops, nattempts)
        for probe in tr_body:
            hop = probe['hop']-1
            attempt = probe['attempt']-1
            rtt[hop][attempt] = probe['rtt_ms']
            ipaddrs[hop][attempt] = probe['ip_addr']

        # --- Set up flag image-file names ---
        # icon_prefix = "../ge/"
        # icon_suffix = "8x8.png"

        # display the table
        print '<br><br><table style="border-spacing: 15px 0px;"><tr><th align="left"><a href="../faq.html#Hop">Hop</a></th>'
        print '<th align="left"><a href="../faq.html#IPAddress">IP Address</a></th><th> </th>'
        print '<th align="center" width=50><a href="../faq.html#MinimumLatency">Min. Latency</th>'
        print '<th align="left"><a href="../faq.html#Carrier">Carrier</a></th><th align="left"><a href="http://maps.google.ca">Location</a></th>'
        print '<th align="left"><a href="../technical.html">GeoPrecision</a></th>'
        print '<th align="left"><a href="../faq.html">Hostname</a></th></tr>'


        for hop in range(nhops):

            print '<tr align="left"><td>%d</td>' % (hop+1),
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

            ip_info = ixmaps2_tmp.get_ip_addr_info(pr_addr)

            nsa_icon     = icon_prefix + ixmaps2_tmp.nsa_flag_colour(ip_info) + icon_suffix
            country_icon = icon_prefix + ixmaps2_tmp.country_flag_colour(ip_info) + icon_suffix
            chotel_icon  = icon_prefix + ixmaps2_tmp.chotel_flag_colour(ip_info) + icon_suffix
            
#            if geo_precision == 'building_level':
#                chotel_icon = icon_prefix + 'carrierhotel_small' + icon_suffix
#            else:
#                chotel_icon = icon_prefix + 'clear' + icon_suffix


            if pr_addr:
                pr_addr = str(pr_addr)
            else:
                pr_addr = "NoResponse"
            print '<td align="left">%s</td>' % (pr_addr+mixed),
#            print '<td align="center">%s</td>' % a_info['hostname'],

            print "<td align=\"left\" style='white-space:nowrap'>",
            print "<img width='10' src=\"" + country_icon +"\" />",
            print "<img width='10' src=\"" + chotel_icon + "\" />",
            print "<img width='10' src=\"" + nsa_icon +    "\" />",
            print "</td>"


# GeoPrecision, but using the old variable name
            if a_info['certainty'].isdigit():
                lat_digits = len(a_info['lat']) - a_info['lat'].find('.') - 1
                long_digits = len(a_info['long']) - a_info['long'].find('.') - 1
                if lat_digits >= 5 or long_digits >= 5:
                    geo_precision = 'building level'
                elif lat_digits <= 2 or long_digits <= 2:
                    geo_precision = 'city level'
                else:
                    geo_precision = 'postal code level'         #don't know if this condition will ever occur...
            else:
                geo_precision = 'Maxmind'

# Jitter, replace as necessary
#
#            if min_latency == '*':
#                jitter = '*'
#            else:
#                jitter = ((int(rtt[hop][0])+int(rtt[hop][1])+int(rtt[hop][2])+int(rtt[hop][3]))/4)-int(min_latency)
#            print '<td>%s</td>' % jitter
            #this is correct, based on 4 attempts in each hop, divided by 4 for the avg. min_latency is still wrong

# Certainty, removed for now (replaced with precision, but we may want both at some point)
#
#            if a_info['certainty'].isdigit():
#                certainty_rating = get_certainty_value(a_info['certainty'])
#            elif a_info['certainty'] == 'None' or a_info['certainty'] == '':
#                certainty_rating = 'MaxMind'
#            else:
#                certainty_rating = 'unknown'
#            print '<td>%s</td>' % certainty_rating
            
            
            min_latency = get_min_latency(hop, rtt, nhops)
            

            if a_info['city'] == '':                    #this check is for if the lat/long is 38/-97
                location = 'unknown'
            else:
                location = a_info['city'] + ' ' + a_info['state']

            sanitized_ISP = ''
            if (a_info['asnum'] == '-1' or a_info['asnum'] == '0'):
                sanitized_ISP = 'not listed by Maxmind'
            else:
                sanitized_ISP = a_info['ISP']
                
            print '<td align="center">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>' % \
                  (min_latency, sanitized_ISP, location, geo_precision, a_info['hostname'])
            
            print "</tr>"
        print "</table>"
        print legend_text

    except TracerouteException:
        print tr_response_not_found


# this is extremely out of date... 
def show_grp_traceroutes(conn, submitter, zip_code):
    print grp_response_begin
    try:
        tr_grp = get_traceroute_grp(conn, submitter, zip_code)

        last_id = 0
        tr_grp_tmp = []

        # --- Conglomerate countries & remove duplicates ---
        for aa in range (len(tr_grp)):
            if tr_grp[aa]['id'] == last_id:

                # -- Add this country to list --
                tr_grp_tmp[-1]['countries_list'].append(tr_grp[aa]['country_code'])
                continue

            else:
                # -- Remember this ID for next round --
                last_id = tr_grp[aa]['id']

                # -- Add this to new list --
                tr_grp_tmp.append(tr_grp[aa])

                tr_grp_tmp[-1]['countries_list'] = []
                tr_grp_tmp[-1]['countries_list'].append (tr_grp[aa]['country_code'])

        tr_grp = tr_grp_tmp

        print show_tr_group_hdr(tr_grp, submitter, zip_code)

        if submitter:
            key = 'zip_code'
        else:
            key = 'submitter'

        print '<form name="input" action="http://test.n-space.org/ixmaps/cgi-bin/ge-render.cgi?traceroute_id=783" method="get">'
        print "<table border='0'>"
        print "<tr><th>&nbsp;</th><th>ID</th><th>&nbsp;</th><th>Date/Time</th><th>%s</th><th>Destination</th></tr>" % key

        for tr in tr_grp:
            
            chotel_icon = canada_icon = us_icon =\
            nsa_icon = icon_prefix + "nsa_small" + icon_suffix;

            nsa_colour =    "clear_small"
            chotel_colour = "clear_small"
            canada_flag   = "clear_small"
            us_flag =       "clear_small"

            if tr['nsa'] == 't':
                nsa_colour = "nsa_small"
            if tr['hotel'] == 't':
                chotel_colour = 'carrierhotel_small'
            try:
                tr['countries_list'].index('CA')
                canada_flag = 'CA'
            except:
                pass
            try:
                tr['countries_list'].index('US')
                us_flag = 'US'
            except:
                pass

            nsa_icon     = icon_prefix + nsa_colour + icon_suffix
            chotel_icon  = icon_prefix + chotel_colour + icon_suffix
            canada_icon  = icon_prefix + canada_flag + icon_suffix
            us_icon      = icon_prefix + us_flag + icon_suffix

            #submitter = sanitize_str(tr['submitter'])
            #zip_code = sanitize_str(tr['zip_code'])
            key_val = sanitize_str(tr[key])
            dest = sanitize_str(tr['dest'])
            if dest == tr['dest_ip']:
                suffix = ""
            else:
                suffix = " [%s]" % tr['dest_ip']

            print "<tr>"

            print '<td><input type="checkbox" name="traceroute_id" value="' \
                  + str(tr['id']) + '" /></td>'
            print "<td>", anchor_tr(tr['id'], str(tr['id'])), "</td>",
            print "<td align=\"center\">",
            print "&nbsp;"
            print "<img width='10' src=\"" + nsa_icon +    "\" />",
            print "<img width='10' src=\"" + chotel_icon + "\" />",
            print "<img src=\"" + us_icon +"\" /> <img src=\"" + canada_icon + "\" />",
            print '&nbsp;'
            print "</td>"

            print "<td>%.16s</td><td>%s</td><td>%s%s</td><td>%s</td></tr>" \
                  % (tr['sub_time'], key_val, dest, suffix)

        print "</table>"
        print '<input type="submit" value="Submit" />'
        print "</form>"
#    print legend_text
    except TracerouteException:
        print grp_response_not_found

icon_prefix = "../ge/"
icon_suffix = '.png'


legend_text="""
  <p>
  <br>
  <table>
    <tr><th colspan="4" align="left">Legend </th></tr> 
    <tr>
      <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>
      <td><img width='10' src="%snsahigh%s"></td>
      <td>NSA:</td><td>Known NSA listening facility in the city</td></tr>
    <tr>
      <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>
      <td><img width='10' src="%snsalow%s"></td>
      <td>NSA:</td><td>Suspected NSA listening facility in the city</td></tr>
    <tr>
      <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>
      <td><img width='10' src="%scarrierhotel_small%s">&nbsp;</td>
      <td>Hotel:</td><td>Carrier hotel exchange point</td></tr>
  </table>
  <br><br><br>
  </p>
""" % (icon_prefix, icon_suffix, icon_prefix, icon_suffix, icon_prefix, icon_suffix)

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
  <h2>Traceroute detail</h2>"""
  
tr_response_not_found="""<p>No data found for that traceroute</p>"""

grp_response_begin="""<html>
 <head>
  <title>Traceroutes available</title>
 <head>
 <body>
  <h2>Available traceroutes</h2>"""

grp_response_not_found="""<p>No traceroutes found</p>"""

response_end="""  
</body>
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
    pass
    show_grp_traceroutes(conn, submitter, '') 
elif zip_code:
    pass
    show_grp_traceroutes(conn, '', zip_code) 
elif form.getfirst("all_submitters"):
    print response_begin % ('submitters', 'submitters')
    sl = get_traceroute_submitters(conn)
    print """<p>To view this data graphically, you must have <a href="http://earth.google.com/download-earth.html">Google Earth</a> downloaded and installed :</p>
     <ol>
     <li>click on: any submitter name (eg AndrewC).</li>
     <li>click on: any id number (eg 1874 	2009-12-13 12:15	M5S2M8	www.wikipedia.com [208.80.152.2])</li>
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

print MAX_MIND_ATTRIBUTION
print """<br><br><a href="http://ixmaps.ischool.utoronto.ca/cgi-bin/tr-detail-tech.cgi?traceroute_id=%s"> Technical version <href>""" % traceroute_id
print response_end

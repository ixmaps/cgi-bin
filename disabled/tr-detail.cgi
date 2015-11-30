#!/usr/bin/python

#FIXME  errors should never give a 2xx response

import sys
import pg
import time
import cgi
import cgitb; cgitb.enable()
import ixmaps
import sys
import math
import re
import ixmaps
from ixmaps import sanitize_str, xml_utils

class TracerouteException(Exception):
    pass

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

    qres = conn.query(qstr)

    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise TracerouteException, "failed to find any traceroutes"
    return qres.dictresult()

def show_tr_group_hdr(tr_grp, submitter, zip_code):
    if submitter:
        whence = "user " + submitter
    else:
        whence = "location " + zip_code
    return "%d traceroutes submitted for %s" % (len(tr_grp), whence)

def get_traceroute_submitters(conn):
    qstr = "select count(*), submitter from traceroute group by submitter order by submitter"
    return _get_traceroute_unique_fld(conn, qstr)

def _get_traceroute_unique_fld(conn, qstr):
    qres = conn.query(qstr)
    return qres.dictresult()

def anchor_submitter(id):
    text = id
    if not text:
        text = " "
    text = sanitize_str(text)
    return '<a href="tr-detail.cgi?submitter=%s">%s</a>' % (id, text)

def array_2d(rows, cols):
    a=[None]*rows
    for i in range(rows):
        a[i] = [None]*cols
    return a

def anchor_tr(id, text):
    return '<a href="tr-detail.cgi?traceroute_id=%d">%s</a>' % (id, text)

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


def get_country_flag (ipInfo=None, ip=None, conn=None):
    
    country = ixmaps.get_country (ipInfo, ip, conn)            

    # print country

    if country == "CA":
        flag = "canadaflag_small"
    elif country == "US":
        flag = "usflag_small"
    else:
        flag = "clear"

    return flag

def get_chotel_flag (ipInfo=None, ip=None, conn=None):
    if ixmaps.is_chotel (ipInfo, ip, conn):
        return "carrierhotel_small"
    else:
        return "clear"


def get_nsa_flag (ipInfo=None, ip=None, conn=None):
    if not ixmaps.is_nsa (ipInfo, ip, conn):
        return "clear"

    else:
        return ( "nsa_class_" + ixmaps.get_nsa_class (ipInfo, ip, conn) )

def get_geo_precision (certainty, lat, long):
    if (type (certainty) is str) and certainty.isdigit():
        lat_digits = len(lat) - lat.find('.') - 1
        long_digits = len(long) - long.find('.') - 1
        if lat_digits >= 5 or long_digits >= 5:
            geo_precision = 'building level'
        elif lat_digits <= 2 or long_digits <= 2:
            geo_precision = 'city level'
        else:
            geo_precision = 'postal code level'         #don't know if this condition will ever occur...
    else:
        geo_precision = 'Maxmind'

    return geo_precision



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

#this needs work FIXME
        print '<form name="input" action="/cgi-dev-bin/ge-render.cgi?traceroute_id=783" method="get">'
        print "<table border='0'>"
        print "<tr><th style='padding-left:0.5em'>&nbsp;</th><th >ID</th><th>&nbsp;</th><th style='padding-left:0.5em'>Date/Time</th><th style='padding-left:0.5em'>%s</th><th style='padding-left:0.5em'>Destination</th></tr>" % key

        for tr in tr_grp:
            
            chotel_icon = canada_icon = us_icon =\
            nsa_icon = ICON_PREFIX + "NSA1" + ICON_SUFFIX;

            nsa_colour =    "clear_small"
            chotel_colour = "clear_small"
            canada_flag   = "clear_small"
            us_flag =       "clear_small"

#what in the hell is this? What is t? Where is it coming from?
#for now, this only works with 
            if tr['nsa'] == 't':
                nsa_colour = "nsahigh"
            if tr['hotel'] == 't':
                chotel_colour = 'carrierhotel_small'
            try:
                tr['countries_list'].index('CA')
                canada_flag = 'canadaflag_small'
            except:
                pass
            try:
                tr['countries_list'].index('US')
                us_flag = 'usflag_small'
            except:
                pass

            nsa_icon     = ICON_PREFIX + nsa_colour + ICON_SUFFIX
            chotel_icon  = ICON_PREFIX + chotel_colour + ICON_SUFFIX
            canada_icon  = ICON_PREFIX + canada_flag + ICON_SUFFIX
            us_icon      = ICON_PREFIX + us_flag + ICON_SUFFIX

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

            print "<td>%.16s</td><td>%s</td><td>%s</td><td>%s</td></tr>" \
                  % (tr['sub_time'], key_val, dest, suffix)

        print "</table>"
        print '<input type="submit" value="Submit" />'
        print "</form>"
#    print legend_text
    except TracerouteException:
        print grp_response_not_found

ICON_PREFIX = "../ge/"
ICON_SUFFIX = '.png'


def html_legend ( ):

    legend_text="""
  <p>
  <br/>
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
  <br/><br/><br/>
  </p>
""" % (ICON_PREFIX, ICON_SUFFIX, ICON_PREFIX, ICON_SUFFIX, ICON_PREFIX, ICON_SUFFIX)

    return legend_text

response_begin="""<html>
 <head>
  <title>%s</title>
 <head>
 <body>
  <h2>%s</h2>
"""

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

conn = ixmaps.DBConnect.getConnection ( )

def html_traceroute_detail_overview (route_overview):
    html = xml_utils ( )
    doc = ''

    id = route_overview['id']

    destination = ( '<b>' + route_overview['dest'] 
                    + '</b> [' + route_overview['dest_ip'] +']' )
                    
    # --- Display function name ---
    doc += html.comment (sys._getframe().f_code.co_name + ' ( )')

    doc += html.tag ('table border="0" width="100%"')
    doc += html.tag ('tr')
    doc += html.tagged_text ('td width="1"', 'Traceroute&nbsp;id:')
    doc += html.tag ('td')
    doc += html.tagged_text ('b', id)
    doc += html.end_tag ('/td')
    doc += html.tagged_text ('td colspan="3" align="right"', 
                             'a href="./ge-render.cgi?traceroute_id=' 
                             + str(id) + '"', 'b', 'Open in Google Earth')

    doc += html.end_tag ('/tr')

    doc += html.tag ('tr')
    doc += html.tagged_text ('td', 'origin:')
    doc += html.tagged_text ('td', 'b', route_overview['zip_code'])
    doc += html.tagged_text ('td width="1"','destination:')
    doc += html.tagged_text ('td', destination)
    doc += html.tagged_text ('td width="150"', '&nbsp;')
    doc += html.end_tag ('/tr')

    doc += html.tag ('tr')
    doc += html.tagged_text ('td', 'submitted&nbsp;by:')
    doc += html.tagged_text ('td', route_overview['submitter'])
    doc += html.tagged_text ('td', 'submitted&nbsp;on:')
    doc += html.tagged_text ('td', route_overview['sub_time'] )
    doc += html.tagged_text ('td', '&nbsp;')
    doc += html.end_tag ('/tr')

    doc += html.end_tag ('/table')

    return doc

def html_geek_traceroute_detail_hops (route_hop_attempts):
    html = xml_utils ( )
    doc = ''

    hop_details = ixmaps.get_route_hops (route_hop_attempts, conn)

    (nhops, nattempts) = ixmaps.get_tr_items_dim(route_hop_attempts)   
    rtt = array_2d(nhops, nattempts)
    ipaddrs = array_2d(nhops, nattempts)
    for probe in route_hop_attempts:
        hop = probe['hop']-1
        attempt = probe['attempt']-1
        rtt[hop][attempt] = probe['rtt_ms']
        ipaddrs[hop][attempt] = probe['ip_addr']

    # --- A list of the IP addresses used in this route ---
    #     Note: this func should take route_hops rather than route_hop_attempts 
    #     Note2: This func should only have one of each ip.  
    ip_list = ixmaps.get_available_ip_addresses (route_hop_attempts) 

    # --- A dict containing the IP-address details ---
    ip_details = ixmaps.get_ip_info (conn, ip_list, with_isp=True)

    # --- Display function name ---
    doc += html.comment (sys._getframe().f_code.co_name + ' ( )')

    doc += html.tag ('table border="0"')
    doc += html.tag ('tr')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#Hop"', 'Hop')
    doc += html.end_tag ('/th')
    doc += html.tagged_text ('th', 'a href="../faq.html#IPAddress"', 'IP Address')
    doc += html.tag ('th colspan="4"')
    doc += html.tagged_text ('a href="../technical.html"', 'Round Trip Times')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../technical.html"', 'AS#')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../technical.html"', 'Latitude')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../technical.html"', 'Longitude')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#Hostname"', 'Hostname')
    doc += html.end_tag ('/th')
    
    doc += html.end_tag ('/tr')

    for hop in range (nhops):
        ip = hop_details[hop]['ip_addr']

        are_there_multiple_ips = False
        for attempt in range(nattempts):
            ip_for_this_attempt = ipaddrs[hop][attempt]
            if (ip) and (ip != ip_for_this_attempt):
                are_there_multiple_ips = True
        if are_there_multiple_ips == True:
            ip += 'm'


        s_rtt = []
        for index in range (nattempts):
            if rtt[hop][index] < 0:
                s_rtt.append ('*') 
            else:
                s_rtt.append (str (rtt[hop][index]) )

        doc += html.tag ('tr')
        doc += html.tagged_text ('td', hop)
        doc += html.tagged_text ('td', ip + '&nbsp;') if ip \
            else html.tagged_text ('td', "No response")

        for r in s_rtt:
            doc += html.tagged_text ('td', r)

        doc += html.tagged_text ('td', hop_details[hop]['asnum'] + '&nbsp;')
        doc += html.tagged_text ('td', hop_details[hop]['lat'])
        doc += html.tagged_text ('td', hop_details[hop]['long'] )
        doc += html.tagged_text ('td', hop_details[hop]['hostname'] )

        doc += html.end_tag('/tr')

    doc += html.end_tag ('/table')

    return doc

def html_traceroute_detail_hops (route_hop_attempts):
    html = xml_utils ( )
    doc = ''

    hop_details = ixmaps.get_route_hops (route_hop_attempts, conn)

    (nhops, nattempts) = ixmaps.get_tr_items_dim(route_hop_attempts)   
    rtt = array_2d(nhops, nattempts)
    ipaddrs = array_2d(nhops, nattempts)
    for probe in route_hop_attempts:
        hop = probe['hop']-1
        attempt = probe['attempt']-1
        rtt[hop][attempt] = probe['rtt_ms']
        ipaddrs[hop][attempt] = probe['ip_addr']

    # --- A list of the IP addresses used in this route ---
    #     Note: this func should take route_hops rather than route_hop_attempts 
    #     Note2: This func should only have one of each ip.  
    ip_list = ixmaps.get_available_ip_addresses (route_hop_attempts) 

    # --- A dict containing the IP-address details ---
    ip_details = ixmaps.get_ip_info (conn, ip_list, with_isp=True)

    # --- Display function name ---
    doc += html.comment (sys._getframe().f_code.co_name + ' ( )')

    doc += html.tag ('table border="0"')
    doc += html.tag ('tr')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#Hop"', 'Hop')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#IPAddress"', 'IP Address')
    doc += html.end_tag ('/th')
    doc += html.tagged_text ('th', '&nbsp;' )
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#MinimumLatency"', 'Min. Latency')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#Carrier"', 'Carrier')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="http://maps.google.com"', 'Location')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../technical.html"', 'GeoPrecision')
    doc += html.end_tag ('/th')
    doc += html.tag ('th')
    doc += html.tagged_text ('a href="../faq.html#Hostname"', 'Hostname')
    doc += html.end_tag ('/th')
    
    doc += html.end_tag ('/tr')

    for hop in range (nhops):
        min_latency = get_min_latency(hop, rtt, nhops)

        certainty = hop_details[hop]['certainty'] if 'certainty' in hop_details[hop] \
            else None

        geo_precision = get_geo_precision(certainty, 
                                          hop_details[hop]['lat'], 
                                          hop_details[hop]['long'])

        city = hop_details[hop]['city'] + ' ' + hop_details[hop]['region']
        if re.match (r'^ +$', city):
            city = ''

        ip = hop_details[hop]['ip_addr']
        try:
            if ip and int(ip_details[ip]['asnum'] >= 1):
                isp = ip_details[ip]['name'] 
            else:
                isp = "Not listed by Maxmind."
        except KeyError:
            isp = "Not listed by Maxmind."

        country_icon = ''
        if ip and ip in ip_details:
            country_icon = ICON_PREFIX + get_country_flag (ip_details[ip]) + ICON_SUFFIX
            nsa_icon     = ICON_PREFIX + get_nsa_flag(ip_details[ip]) + ICON_SUFFIX
            chotel_icon  = ICON_PREFIX + get_chotel_flag(ip_details[ip]) + ICON_SUFFIX

        else:
            country_icon = ICON_PREFIX + 'clear' + ICON_SUFFIX
            nsa_icon =     ICON_PREFIX + 'clear' + ICON_SUFFIX
            chotel_icon =  ICON_PREFIX + 'clear' + ICON_SUFFIX

        doc += html.tag ('tr')
        doc += html.tagged_text ('td', hop)
        doc += html.tagged_text ('td', ip) if ip \
            else html.tagged_text ('td', "No response")
        doc += html.tag ('td align="center" style="white-space:nowrap"')
        doc += html.empty_tag ('img width="10" src="' + country_icon + '"', 
                               'img width="10" src="' + chotel_icon + '"',
                               'img width="10" src="' + nsa_icon + '"')

        doc += html.end_tag ('/td')
        doc += html.tagged_text ('td align="center"', min_latency)
        doc += html.tagged_text ('td', isp)
        doc += html.tagged_text ('td', city) if city \
            else html.tagged_text ('td', 'Unknown')
        doc += html.tagged_text ('td', geo_precision)
        doc += html.tagged_text ('td', hop_details[hop]['hostname'] )

        doc += html.end_tag ('/tr')

    doc += html.end_tag ('/table')

    return doc

def main (traceroute_id, submitter, zip_code, all_submitters, geek=False):

    conn = ixmaps.DBConnect.getConnection ( )

    print "Content-Type: text/html\n"

    # --- If 'all_submitters' is set, this trumps the other variables ---
    if all_submitters:
        # print response_begin % ('submitters', 'submitters')
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

        return

    elif submitter or zip_code:

        show_grp_traceroutes (conn, submitter, zip_code)
        return

    route_hop_attempts = ixmaps.get_tr_items (conn, traceroute_id)
    # route_hops = ixmaps.get_route_hops (route_hop_attempts, conn)
    route_overview = ixmaps.get_traceroute (conn, traceroute_id)

    if (not geek):
        title = "Traceroute detail"
    else:
        title = "Traceroute detail--technical version"

    html = xml_utils ( )
    doc = ''

    doc += html.tag('html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en"')

    doc += html.tag("head")

    doc += html.tagged_text ("title", title)

    doc += html.end_tag ("/head")

    doc += html.tag ("body")
    doc += html.tagged_text ('h2', title)

    doc += html_traceroute_detail_overview (route_overview)

    doc += html.empty_tag ('br', 'br')

    if (not geek):
        doc += html.indent (html_traceroute_detail_hops (route_hop_attempts) )

    else:
        doc += html.indent (html_geek_traceroute_detail_hops (route_hop_attempts) )

    if not geek:
        doc += html.indent (html_legend ( ) )

    doc += html.tag ('p')
    # doc += html.indent (MAX_MIND_ATTRIBUTION)
    doc += html.indent (ixmaps.html_max_mind_attribution ( ) )
    doc += html.end_tag ('/p')

    if geek:
        doc += html.tag ('p')
        doc += html.text ('You can also look up traceroutes by')
        doc += html.tagged_text ('a href="/cgi-bin/tr-distance.cgi"', 
                                 'geographic proximity')
        doc += html.text ('to a location.')
        doc += html.end_tag ('/p')

    doc += html.empty_tag ('br')

    if not geek:
        doc += html.tagged_text ('p', 'a href="/cgi-bin/tr-detail.cgi?traceroute_id=' 
                                 + str(traceroute_id) + '&geek=true', 
                                 'Technical version' )
    else:
        doc += html.tagged_text ('p', 'a href="/cgi-bin/tr-detail.cgi?traceroute_id=' 
                                 + str(traceroute_id), 
                                 'Standard version' )
        

    doc += html.end_tag ("/body")
    doc += html.end_tag ("/html")

    print doc

if __name__ == "__main__":
    # -- Get CGI variables --
    form = cgi.FieldStorage()
    traceroute_id = (form.getfirst("traceroute_id") )
    submitter = form.getfirst("submitter")
    zip_code = form.getfirst("zip_code")
    all_submitters = form.getfirst ("all_submitters")

    # --- Convert traceroute from string to int ---
    if traceroute_id != None:
        traceroute_id = int (traceroute_id)
        
    is_geek_mode_on = False if (form.getfirst ("geek") != "true" ) else True

    # all_submitters = 1
    # submitter = "AndrewC"

    main (traceroute_id, submitter, zip_code, all_submitters, geek=is_geek_mode_on) 

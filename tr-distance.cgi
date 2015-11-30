#!/usr/bin/python

import pg
import sys
import math
import time
import cgi
import cgitb; cgitb.enable()
from ixmaps import DBConnect, ll_to_xyz, km_to_degrees, distance_km, sanitize_str, dist_unit_to_km

# persuant to OPEN DATA LICENSE (GeoLite Country and GeoLite City databases)
MAX_MIND_ATTRIBUTION="""
  <br/><br/>
This product includes GeoLite data created by MaxMind, available from
<a href="http://maxmind.com/">http://maxmind.com/</a>
"""

class CHotelException(Exception):
    pass

def get_chotels(conn):
    qres = conn.query("select id,lat,long,address from chotel order by long")
    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise CHotelException, "failed to find any Carrier Hotels"
    return qres.dictresult()

def ubi_est_ch(conn, ch_id):
    qres = conn.query("select lat,long from chotel where id=%d" % ch_id)
    dr = qres.dictresult()[0]
    return (dr['lat'], dr['long'])

def get_tr_close_to(conn, lat, long, radius):
    """Get traceroutes within a given radius of a latitude/longitude pair.

    Both lat, and long are in decimal degrees, north and east positive.
    Radius is in kilometers."""
    ref_xyz = ll_to_xyz(lat, long)
    (deg_lat, deg_long) = km_to_degrees(radius, lat, 1.0)
    square_cos_lat = math.cos(math.pi*lat/180.0)**2

    select_items = "traceroute_id,dest,sqrt((lat- %.8g)*(lat- %.8g)+(long- %.8g)*(long- %.8g)*%g) as dist " \
            % (lat, lat, long, long, square_cos_lat)
    from_clause = "from ip_addr_info natural join tr_item join traceroute on tr_item.traceroute_id=traceroute.id "
    where_clause = "where abs(lat- %.8g) < %.8g and abs(long - %.8g) < %.8g " % (lat, deg_lat, long, deg_long)
    order_clause = "order by dist,dest"
    qstr = "select distinct "+select_items+from_clause+where_clause+order_clause

    #qstr="select distinct traceroute_id,dest,sqrt((lat-39.0)*(lat-39.0)+(long - -77.0)*(long - -77.0)) from ip_addr_info natural join tr_item join traceroute on tr_item.traceroute_id=traceroute.id where abs(lat-39.0) < 1.0 and abs(long - -77.0) < 1.0 order by sqrt,dest"

    print qstr+"<br/><br/>"
    qres = conn.query(qstr)
    #print qres.dictresult()
    return qres.dictresult()

def fmt_ch_selection(conn):
    chotels = get_chotels(conn)
    print '    <p>'
    for ch in chotels:
        print '    <input type="radio" name="ch_id" value="%(id)d" />[%(id)d] (%(lat).5f,%(long).5f) %(address)s<br/>' % ch
   
    print '    <input type="radio" name="ch_id" value="0" checked />Enter lat/long below<br/>'
    print '    </p>'

form_begin="""<html>
 <head>
  <title>Traceroute location selection</title>
 <head>
 <body>
  <h2>Geolocated Traceroutes passing near Carrier Hotels</h2>
  <form method="POST">
   <p>Traceroutes passing within
   <input type="text" name="radius" size="10" value="1.0"/>
   <select name="rad_unit">
    <option>km</option>
    <option>m</option>
    <option>mi</option>
    <option>ft</option>
   </select>
   of<p/>
"""

form_end="""<br/>
   Position in decimal degrees</br>
   Latitude (positive North)&nbsp;
   <input type="text" name="pos_lat" size="10" value=""/>
   Longitude (positive East)&nbsp;
   <input type="text" name="pos_long" size="10" value=""/>
   <input type="submit" />
  </form>
 </body>
</html>"""

response_begin="""<html>
 <head>
  <title>Traceroutes passing near a geographic location</title>
 <head>
 <body>
  <h2>Available Traceroutes</h2>
"""

response_not_found="""<p>No data found near there</p>"""

response_end=""" </body>
</html>"""

def anchor_tr(id, text):
    return '<a href="tr-detail.cgi?traceroute_id=%d">%s</a>' % (id, text)

def print_result_table(tr_close, rad_unit, deg_to_km):
    # the dist field in rows of tr_close are in degrees of arc along the Earth's surface
    scale = deg_to_km / dist_unit_to_km(rad_unit)
    already_seen=set()
    print '<table><tr><th>ID</th><th>destination</th><th>distance (%s)</th></tr>\n' % rad_unit
    for tr in tr_close:
        id = tr['traceroute_id']
        if id not in already_seen:
            already_seen.add(id)
            link = anchor_tr(id, str(id))
            print '<tr><td>%s</td><td>%s</td><td>%.4g</td></tr>\n' % (link, tr['dest'], scale*tr['dist'])
    print '</table>'
    print MAX_MIND_ATTRIBUTION

conn = DBConnect.getConnection()

print "Content-Type: text/html"
print 

form = cgi.FieldStorage()

is_starting = False
try:
    ch_id = int(form.getfirst("ch_id"))
    try:
        radius = float(form.getfirst("radius"))
    except ValueError:
        radius = 1.0
    rad_unit = sanitize_str(form.getfirst("rad_unit"))
    radius *= dist_unit_to_km(rad_unit)
    if ch_id > 0:
        (pos_lat, pos_long) = ubi_est_ch(conn, ch_id)
    else:
        pos_lat = float(form.getfirst("pos_lat"))
        pos_long = float(form.getfirst("pos_long"))
    # do some sanity checking
    if radius < 0 or radius > 1000.0:
        is_starting = True
    if pos_long < -180.0 or 180.0 < pos_long or pos_lat < -75.0 or 75.0 < pos_lat:
        is_starting = True
except TypeError:
    is_starting = True

if is_starting:
    print form_begin
    fmt_ch_selection(conn)
    print form_end
else:
    print response_begin
    tr_close = get_tr_close_to(conn, pos_lat, pos_long, radius)
    if len(tr_close) > 0:
        (deg_lat, deg_long) = km_to_degrees(1.0, pos_lat)
        # only need deg_lat as it is a good first order approximation to the Earth's curvature
        print_result_table(tr_close, rad_unit, 1.0/deg_lat)
    else:
        print response_not_found
    print response_end
    

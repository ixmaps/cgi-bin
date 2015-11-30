#!/usr/bin/python

"""
Render a traceroute for display by Google Earth.
"""

import pg
import time
import cgi
import math
import string
import cgitb; cgitb.enable()
import sys
import re
from cStringIO import StringIO

import ixmaps
from ixmaps import xml_utils

# persuant to OPEN DATA LICENSE (GeoLite Country and GeoLite City databases)
MAX_MIND_ATTRIBUTION="""
<br/><br/>
This product includes GeoLite data created by MaxMind, available from
<a href="http://maxmind.com/">http://maxmind.com/</a>
"""

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# def ll_to_xyz(lat, long):
    # lat_radians = math.pi * lat / 180.0
    # long_radians = math.pi * long / 180.0
    # x = EARTH_MEAN_RADIUS * math.cos(long_radians) * math.cos(lat_radians)
    # y = EARTH_MEAN_RADIUS * math.sin(long_radians) * math.cos(lat_radians)
    # z = EARTH_MEAN_RADIUS * math.sin(lat_radians)
    # return (x,y,z)

# def km_to_degrees(km, lat, scale=1.0):
    # deg_lat = scale*km*180.0/(EARTH_MEAN_RADIUS*math.pi)
    # deg_long = deg_lat / math.cos(math.pi*lat/180.0)
    # return (deg_lat, deg_long)

# def distance_km(pos1, pos2):
    # dx = pos2[0]-pos1[0]
    # dy = pos2[1]-pos1[1]
    # dz = pos2[2]-pos1[2]
    # return math.sqrt(dx*dx+dy*dy+dz*dz)

# def ll_line_to_km (ll1, ll2):
    # pos1 = ll_to_xyz (ll1[0], ll1[1])
    # pos2 = ll_to_xyz (ll2[0], ll2[1])
    # return distance_km (pos1, pos2)


# ----------------------------------------------------------------------------


class TracerouteException(Exception):
    pass

# class DBConnect(object):
    # conn = None
    # def getConnection():
        # if not DBConnect.conn:
            # DBConnect.conn = pg.connect("ixmaps", "localhost", 5432)
        # return DBConnect.conn
    # getConnection = staticmethod(getConnection)

def get_http_header (traceroute_id=None):
    if traceroute_id:
        ret = 'Content-Disposition: inline; filename="IXmaps_GE%d.kml"\n' % traceroute_id[idlist]
    else:
        ret = 'Content-Disposition: inline; filename="IXmaps_GE.kml"\n'
    ret += "Content-Type: application/vnd.google-earth.kml+xml; charset=UTF-8"
    ret += "\n"

    return ret

def get_tr_items_dim(da):
    """da is array of dicts, each dict representing a single traceroute probe"""
    nhops = nattempts = 0
    for d in da:
        if d['attempt'] > nattempts:
            nattempts = d['attempt']
        if d['hop'] > nhops:
            nhops = d['hop']
    return (nhops, nattempts)


def get_tr_item_count(conn, id):
    qstr = "select count(*) from tr_item where traceroute_id=%d" % id
    qres = conn.query(qstr)
    ent = qres.dictresult()[0]
    return ent['count']
    
def array_2d(rows, cols):
    a=[None]*rows
    for i in range(rows):
        a[i] = [None]*cols
    return a

# def get_ip_addr_info (conn, addr):
    # # print "IP: " + str(addr)

    # if addr:
        # # print "addr: " + str(addr)
        # qres = conn.query("select * from ip_addr_info where ip_addr='%s'" % addr)
        # d = qres.dictresult()[0]
        # d['ip_addr'] = addr
        # d['hostname'] = str(d['hostname'])
        # d['lat'] = str(d['lat'])
        # d['long'] = str(d['long'])
        # d['asnum'] = str(d['asnum'])
        # d['country'] = str(d['mm_country'])
        # d['region'] = str(d['mm_region'])
        # d['city'] = str(d['mm_city'])
        # d['pcode'] = str(d['mm_postal'])
        # d['area_code'] = str(d['mm_area_code'])
        # d['dma_code'] = str(d['mm_dma_code'])
        # d['override'] = str(d['gl_override'])

    # else:
        # d={'lat': '', 'hostname': '', 'ip_addr': None, 'long': '', 'asnum': '',
           # 'region': '', 'city': '', 'country': '', 'pcode': '', 'area_code': '', 'dma_code': '', 'override': ''}
        
    # return d

def get_complete_traceroute(conn, traceroute_id):
    tr_header = ixmaps.get_traceroute(conn, traceroute_id)
    tr_body = ixmaps.get_tr_items(conn, traceroute_id)
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
    return (tr_header, tr_body, nhops, nattempts, rtt, ipaddrs)

def is_accurate_to (places, x):
    X = x * math.pow (10, places)
    if (int(X) % 10) != 0:
        return True
    else:
        return False
    

# --- Note: not currently in use: Remove? ---
class Proximities(object):
    def __init__(self):
        self.pa = []
        self.reset()
    def add(self, id, p1, p2):
        self.pa.append((id, p1,p2))
    def reset(self):
        self.index = 0
    def idExists(self, id):
        retVal = False
        for i in self.pa:
            if i[0] == id:
                retVal = True
                break
        return retVal
    def __iter__(self):
        return self
    def next(self):
        try:
            item = self.pa[self.index]
            self.index += 1
            return item
        except IndexError:
            raise StopIteration

def get_lat_long (hdesc):
    if 'lat' in hdesc and 'long' in hdesc:
        return (hdesc['lat'], hdesc['long'])

def get_ch_class(chotel):
    """Determine styling class for a carrier hotel."""

    if chotel['type'] == 'NSA':
        if chotel['nsa'] == 'A': 
            ixclass = 'NSA1'
        elif chotel['nsa'] == 'B':
            ixclass = 'NSA2'
        else:
            ixclass = 'NSA3'

    elif chotel['type'] == 'UC':
        ixclass = 'UC'

    elif chotel['type'] == 'Google':
	ixclass = 'AGF'

    elif chotel['type'] == 'CH':
        ixclass = 'chotel'

    else:
        ixclass = 'OTH'
    return ixclass

def URL_encode_ampersands(url):
    return "&amp;".join(url.split("&"))
        
class CHotels(object):
    """    A class for returning lists or dicts containing different subsets
    of the ixmaps-database carrier-hotels."""

    def __init__(self, conn=None, chotels=None):
        if (conn):
            qres = conn.query("select * from chotel")
            try:
                id = qres.dictresult()[0]['id']
            except IndexError:
                raise TracerouteException, "failed to find any carrier hotels"
            self.chotels = qres.dictresult ( )

        elif type(chotels) == list:
            self.chotels = chotels

        elif type(chotels) == dict:
            chotel_list = []
            for chotel in chotels:
                chotel_list.append (chotels[chotel] )
            self.chotels = chotel_list

        else:
            raise TracerouteException, "No database specified, and no traceroute-list given."
            
        location_styles = facility_icons ( )
        for ch in self.chotels:
            ch['xyz'] = ixmaps.ll_to_xyz(ch['lat'], ch['long'])
            # ch['to_render'] = False
            ixclass = get_ch_class(ch)
            ch['ixclass'] = string.replace(ixclass, "near", "", 1)
            ch['facility'] = location_styles[ch['ixclass']]['facility']
            ch['image_esc'] = URL_encode_ampersands(ch['image']) if (ch['image']) else ''
        self.reset()

    def reset(self):
        self.index = 0

    def __iter__(self):
        return self

    def next(self):
        try:
            chotels = self.chotels
            index = self.index
            # while not chotels[index]['to_render']:
                # index += 1
            item = chotels[index]
            index += 1
            self.index = index
            return item
        except IndexError:
            raise StopIteration

    def nearest(self, longitude, latitude, km_radius=ixmaps.EARTH_EQUAT_RADIUS*2):
        """Find the nearest carrier hotel that's within a given radius in km."""
        point = ixmaps.ll_to_xyz(latitude, longitude)
        max_dist = km_radius
        chotel = None
        for ch in self.chotels:
            dist = distance_km(point, ch['xyz'])
            if dist < max_dist:
                #print ch['id'], ch['long'], ch['lat'], dist, max_dist
                max_dist = dist
                chotel = ch
        return chotel
        
    def all_within_by_id (self, longitude, latitude, km_radius=ixmaps.EARTH_EQUAT_RADIUS*2):
        """ Create a dict of carrier hotels within a given radius,
            sorted by carrier-hotel id."""
        chotel_list = self.all_within (longitude, latitude, km_radius)

        chotel_dict = {}
        for chotel in chotel_list:
            chotel_dict[chotel['id']] = chotel

        return chotel_dict

    def all_within (self, longitude, latitude, km_radius=ixmaps.EARTH_EQUAT_RADIUS*2, set_to_render=False):
        """Create a list of carrier hotels within a given radius in km."""
        point = ixmaps.ll_to_xyz(latitude, longitude)
        chotel = None
        chotel_tuple_list = [ ]

        # --- Create list of chotels within radius ---
        for ch in self.chotels:
            dist = ixmaps.distance_km (point, ch['xyz'] )
            if dist < km_radius:
                chotel_tuple_list.append ( (dist, ch) )

        # --- Sort chotels list ---
        chotel_tuple_list.sort ( )

        # --- Convert to non-tupple by removing distance meta-info ---
        chotel_list = [ ]
        for ch in chotel_tuple_list:
            chotel_list.append (ch[1])

        # --- Set whether to render ---
        for ch in chotel_list:
            if set_to_render:
                ch['networks'] = ''
                # ch['to_render'] = True

        # print chotel_list

        return chotel_list

    def get_type (self, type):
        chotel_list = []

        for chotel in self.chotels:
            if chotel['type'] == type:
                chotel_list.append(chotel)

        return chotel_list

    def get_all (self):
        chotel_list = []

        for chotel in self.chotels:
            chotel_list.append(chotel)

        return chotel_list

def facility_icons():
    icons = {
    'AGF'         : { 'id': 'AGF',         'symbol': 'google',           'facility': '<b>Google facility</b> located in' },
    'nearAGF'     : { 'id': 'nearAGF',     'symbol': 'neargoogle',       'facility': 'Near a Google facility' },
    'CAN'         : { 'id': 'CAN',         'symbol': 'locationcircle',   'facility': 'In Canada' },
    'NSA1'        : { 'id': 'NSA1',        'symbol': 'nsahigh',          'facility': '<img src="http://ixmaps.ischool.utoronto.ca/ge/nsahigh.png" alt="Legend not found"/></br> <b>Known NSA listening post</b> located at' },
    'NSA2'        : { 'id': 'NSA2',        'symbol': 'nsamedium',        'facility': '<b>Likely NSA listening post</b> located in' },
    'NSA3'        : { 'id': 'NSA3',        'symbol': 'nsalow',           'facility': '<b>Possible NSA listening post</b> located in' },
    'CRG'         : { 'id': 'CRG',         'symbol': 'crg',              'facility': 'Owned by Carlyle Real Estate - CoreSite' },
    'nearCRG'     : { 'id': 'nearCRG',     'symbol': 'nearcrg',          'facility': 'Near a facility owned by Carlyle Real Estate - CoreSite' },
    'INT'         : { 'id': 'INT',         'symbol': 'locationcircle',   'facility': '<b>Router</b> located in' },
    'router_1'    : { 'id': 'router_1',    'symbol': 'router_1',         'facility': '<b>Router</b> located in' },
    'router_3'    : { 'id': 'router_3',    'symbol': 'router_3',         'facility': '<b>Router</b> located in' },
    'router_4'    : { 'id': 'router_4',    'symbol': 'router_4',         'facility': '<b>Router</b> located in' },
    'router_other': { 'id': 'router_other','symbol': 'router_4',         'facility': '<b>Router</b> located in' },
    'chotel'      : { 'id': 'chotel',      'symbol': 'carrierhotel',     'facility': '<b>Carrier hotel</b> located at' },
    'UC'          : { 'id': 'UC',          'symbol': 'undersea',         'facility': '<b>Undersea cable landing site</b> located in' },
    'OTH'         : { 'id': 'OTH',         'symbol': 'locationcircle',   'facility': 'Router' },  # other (is this ever used in the current setup?)
        }
    return icons

def kml_hop_style (style):

    kml = xml_utils()
    doc = kml.text()
    doc += kml.comment ('kml_hop_style ({' + str(style['id']) + '})')

    doc += kml.tag('Style id="' + style['id'] + '_nonsel"')
    doc += kml.tag('IconStyle')

    # --- Icons named *_small.png will be enlarged ---
    if not (re.search (r'[-_]small\b', style['symbol'])):
        doc += kml.tagged_text ('scale', 0.8)
    else:
        doc += kml.tagged_text ('scale', 3.0)
    doc += kml.tag ('Icon')
    doc += kml.tagged_text ('href', ixmaps.URL_HOME + '/ge/' + style['symbol'] + '.png')
    doc += kml.end_tag ('/Icon')
    doc += kml.end_tag ('/IconStyle')
    doc += kml.tag ('LabelStyle')
    doc += kml.tagged_text ('scale', 0.8)
    doc += kml.end_tag ('/LabelStyle')
    doc += kml.tag ('BalloonStyle')
    doc += kml.tag ('text')
    doc += kml.cdata ('''<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top">
    <td width="100%" align="left" valign="top">
      <p><a href=\"''' + ixmaps.URL_HOME + '''\"; title="IXmaps">
        <img src=\"''' + ixmaps.URL_HOME + '''ge/ixmaps.png\" alt="" width="270" height="60"></a></p>
      <p>''' + style['facility'] + '''</p> <p><strong>$[name]</strong></p>
      $[description]
    </td></tr></table>''')
    doc += kml.end_tag ('/text')
    doc += kml.end_tag ('/BalloonStyle')
    doc += kml.end_tag ("/Style")

    doc += kml.tag ('Style id="' + style['id'] + '_sel"')
    doc += kml.tag ('IconStyle')

    # --- Icons named *_small.png will be enlarged ---
    if not (re.search (r'[-_]small\b', style['symbol'])):
        doc += kml.tagged_text ('scale', 0.9)
    else:
        doc += kml.tagged_text ('scale', 3.0)
    doc += kml.tag ('Icon')
    doc += kml.tagged_text ('href', ixmaps.URL_HOME + 'ge/' + style['symbol'] + '.png')
    doc += kml.end_tag ('/Icon')
    doc += kml.end_tag ('/IconStyle')
    doc += kml.tag ('LabelStyle')
    doc += kml.tagged_text ('scale', 1.2)
    doc += kml.end_tag ('/LabelStyle')

    doc += kml.tag ('BalloonStyle')
    doc += kml.tag ('text')
    doc += kml.cdata ("""<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top">
    <td width="100%" align="left" valign="top">
      <p><a href=\"""" + ixmaps.URL_HOME + """\"; title="IXmaps"><img src=\"""" + ixmaps.URL_HOME + """ge/ixmaps.png" alt="" width="270" height="60"></a></p>
      <p>""" + style['facility'] + """</p> <p><strong>$[name]</strong></p>
      $[description]</td></tr></table>""")
    doc += kml.end_tag ('/text')
    doc += kml.end_tag ('/BalloonStyle')
    doc += kml.end_tag ('/Style')

    doc += kml.tag ('StyleMap id="' + style['id'] + '"')
    doc += kml.tag ('Pair')

    doc += kml.tagged_text ('key', 'normal')
    doc += kml.tagged_text ('styleUrl', '#' + style['id'] + '_nonsel')
    
    doc += kml.end_tag ('/Pair')

    doc += kml.tag ('Pair')
    doc += kml.tagged_text ('key', 'highlight')
    doc += kml.tagged_text ('styleUrl', '#' + style['id'] + '_sel')

    doc += kml.end_tag ('/Pair')
    doc += kml.end_tag ('/StyleMap')

    return doc 

def xml_document_header():
    kml_header = '<?xml version="1.0" encoding="UTF-8"?>'

    return kml_header

def kml_doc_setup ():
    kml = xml_utils()

    doc = kml.text()
    doc += kml.comment ('kml_doc_setup ( )')

    # --- define KML-document and styles
    doc += kml.text ('<name>Traceroute Results</name>')
    doc += kml.tagged_text ('visibility', '0')
    doc += kml.tagged_text ('open', '1')
    doc += kml.tag ("description")
    doc += kml.text ("Select this folder and click on the &apos;Play&apos; \nbutton below, to start the tour.")
    doc += kml.end_tag ("/description")

    doc += kml.tag ('Camera id="NorthAmerica"')
    doc += kml.tagged_text ('longitude', '-96.0')
    doc += kml.tagged_text ('latitude', '45.0')
    doc += kml.tagged_text ('altitude', '4500000.0')
    doc += kml.tagged_text ('heading', '0.0')
    doc += kml.tagged_text ('tilt', '0')
    doc += kml.tagged_text ('roll', '0')
    doc += kml.tagged_text ('altitudeMode', 'absolute')
    doc += kml.end_tag ('/Camera')

    doc += kml.tag ('Style id="docBalloonStyle"')
    doc += kml.tag ('BalloonStyle')

    doc += kml.comment ("a background colour for the balloon")
    doc += kml.tagged_text ("bgColor", "40ffffbb")
    doc += kml.comment ("Styling of balloon text")
    doc += kml.tag ("text")

    doc += kml.cdata ('''<b><font color="#CC0000" size="+3">$[name]</font></b>
<br/><br/>
<font face="Courier">$[description]</font>
<br/><br/>''')

    doc += kml.end_tag ("/text")

    doc += kml.end_tag ('/BalloonStyle')
    doc += kml.end_tag ('/Style')

    doc += kml.tag ("Style id='trPathStyle'")
    doc += kml.tag ("LineStyle")
    # --- Note: the colour-scheme is transparency-layer, blue, green, red
    doc += kml.tagged_text ("color", "ff2800ff")
    doc += kml.tagged_text ("width", "4")
    doc += kml.end_tag ("/LineStyle")
    doc += kml.end_tag ("/Style")
    
    doc += kml.tag ('Style id="spiderStyle"')
    doc += kml.tag ('LineStyle')
    doc += kml.tagged_text ('color', '7f7ca6e5')
    doc += kml.tagged_text ('width', '4')
    doc += kml.end_tag ('/LineStyle')
    doc += kml.end_tag ('/Style')

    doc += kml.tag ('Style id="ixFolderStyle"')
    doc += kml.end_tag ('/Style')


    return doc


def kml_legend ( ):
    kml = xml_utils()
    doc = ''

    doc += kml.text()

    # --- Display function name ---
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')

    doc += kml.tag ("Document")
    doc += kml.tagged_text ('name', 'Legend')
    doc += kml.tagged_text ('Snippet maxLines="0"', 'Legend')

    doc += kml.tag ("description")

    doc += kml.text ("<![CDATA[")

    doc += kml.text ('''<table>
  <tr>
    <td>
      <img src="http://ixmaps.ischool.utoronto.ca/ge/ixmaps_legend.png"
           alt="Legend not found"/>
    </td>
  </tr>
</table''')
           
    # doc += kml.cdata ("""<img
           # src="http://ixmaps.ischool.utoronto.ca/ge/ixmaps_legend.png"
           # alt="Legend not found"/>""", indent=False)

    doc += kml.text ("]]>")

    doc += kml.end_tag ("/description")
    doc += kml.tagged_text ("styleUrl", "#docBalloonStyle")

    doc += kml.end_tag ("/Document")

    return doc


def kml_traceroute (route_id, chotel_obj, conn, is_open=0):
    """
    Return the KML specific to traceroute 'route_id'.

    Parameters:
    traceroute (int)
    conn 

    Optional parameters:
    is_open (int)
    """ 

    # --- Each hop and each hop-attempt ---
    route_hop_attempts = ixmaps.get_tr_items (conn, route_id) # aka tr_body

    # --- Each hop ---
    #     Note: route_hops needs to contain rtt-info
    #     Note2: you can probably remove conn from this func
    route_hops = get_route_hops (route_hop_attempts, conn)

    # --- A list of the IP addresses used in this route ---
    #     Note: this func should take route_hops rather than route_hop_attempts 
    #     Note2: This func should only have one of each ip.  
    ip_list = ixmaps.get_available_ip_addresses (route_hop_attempts) 

    # --- A dict containing the IP-address details ---
    ip_details = ixmaps.get_ip_info (conn, ip_list)

    dest_hostname = route_hops[len(route_hops)-1]['hostname']

    # --- Create one carrier-hotel object for NSA posts,
    #     and one for generic carrier hotels ---
    ch_chotels_list = chotel_obj.get_type ('CH')
    nsa_chotels_list = chotel_obj.get_type ('NSA') 
    ch_chotels_obj = CHotels (chotels=ch_chotels_list)
    nsa_chotels_obj = CHotels (chotels=nsa_chotels_list)

    doc = ""
    kml = xml_utils ( )

    doc += kml.text ( )

    # --- Display function name ---
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')

    # doc += kml.text ('route_hop_attempts: ' + str(route_hop_attempts))
    # doc += kml.text ('route_hops: ' + str(route_hops))

    doc += kml.tag ('Folder id="route_' + str(route_id) + '"')

    if (dest_hostname):
        doc += kml.tagged_text ('name', 'Rt ' + str(route_id) + " (" +
                                dest_hostname + ")" )
    else:
        doc += kml.tagged_text ('name', 'Rt ' + str(route_id))
        
    doc += kml.tagged_text ("visibility", 0)
    doc += kml.tagged_text ('open', is_open)
    doc += kml.tagged_text ('Snippet', str (len(route_hops) ) + " hops" )
    
    doc += kml.tag ("description")
    doc += kml.text ("<![CDATA[")
    doc += kml.text ('''<table>
  <tr>
    <th>Hop </th> 
    <th>Lat </th>
    <th>Long </th>
    <th>Hostname </th>
  </tr>
  <! -- ?? ... -->
</table>''')
    doc += kml.text ("]]>")
    doc += kml.end_tag ("/description")

    doc += kml.tagged_text ('styleUrl', '#ixFolderStyle')
                     
    # --- Get the set of IP's ---

    # number_of_hops = len ip_list ( )

    # number_of_hops = get_coord_count (conn, route_id)
    number_of_hops = len (route_hops)

    chotels_enroute = {}

    # --- En-route carrier-hotels layer ---
    for placemark in range (number_of_hops):
        ip = route_hops[placemark]['ip_addr']
        if ip:

            # --- Determine all generic carrier hotels near this placemark ---
            nearby_ch_chotels = ch_chotels_obj.all_within_by_id (float(ip_details[ip]['long']),
                    float(ip_details[ip]['lat']), ixmaps.MAX_CHOTEL_DIST)
            
            # --- Determine all NSA posts near this placemark ---
            nearby_nsa_chotels = nsa_chotels_obj.all_within_by_id (float(ip_details[ip]['long']),
                    float(ip_details[ip]['lat']), ixmaps.MAX_NSA_DIST)

            # --- Add these determined facilities to the enroute-chotels layer ---
            chotels_enroute = dict (chotels_enroute.items ( ) +
                                    nearby_ch_chotels.items ( ) +
                                    nearby_nsa_chotels.items ( ) )

    doc +=  kml.tag ("Folder")
    doc +=  kml.tagged_text ('name', 'Facilities en route')
    doc +=  kml.tagged_text ('visibility', 1)
    doc +=  kml.tagged_text ('styleUrl', '#ixFolderStyle')
    for chotel in chotels_enroute:
        doc += kml.indent (kml_chotel_placemarks (chotels_enroute[chotel],
                           add_to_id='_route_' + str(route_id) ) )
    doc += kml.end_tag ("/Folder")

    # --- Create the traceroute-line ---
    doc += kml.indent (kml_placemark_line (route_id, route_hops) )

    # --- Create the hop-placemarks (note: 'placemarks' start from 0,
    #     but 'hops' in the DB and as displayed, start counting from 1) ---
    for placemark in range (number_of_hops):

        ip = route_hops[placemark]['ip_addr']

        if ip:
            doc += kml.indent ( kml_placemark_hop (ip_details[ip],
                                                   route_id, placemark+1,
                                                   route_hops[placemark] ) )

    doc += kml.text ( )
    doc += kml.end_tag ("/Folder")

    return doc

def get_hop_style (ip_info):
    if 'geo_precision' in ip_info:
        if ip_info['geo_precision'] == "building level":
            precision = "1"
        elif ip_info['geo_precision'] == "city level":
            precision = "3"
        elif ip_info['geo_precision'] == "Maxmind" :
            precision = "4"
        else:
            precision == "misc"

    return "router_" + precision


def kml_placemark_hop (ip_info, route, hop, hop_properties):

    # print "ip_info:", ip_info , '\n'
    # print "route:", route, '\n'
    # print "hop:", hop, '\n'
    # print "hop_properties", hop_properties, '\n'

    ip = hop_properties['ip_addr']

    # --- Define 'hostname', but only if ip_info['hostname'] is a
    #     DNS-address (as opposed to an IP) ---
    hostname = ip_info['hostname'] if (re.match 
                                       (r'.+\.[a-zA-Z].*',ip_info['hostname']))\
                                       else None
                                       

    hop_style = get_hop_style (ip_info)

    # ixmaps.ip_info = get_ip_addr_info (ip, conn)

    kml = xml_utils()
    doc = kml.text()

    # --- Display function name ---
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')

    
    doc += kml.tag ('Placemark id="route_' + str(route) + '_hop_'
                    + str(hop) + '"')

    if (hostname):
        # doc += kml.tagged_text ('name', ip + ' (' + hostname + ') ')
        doc += kml.tagged_text ('name', hostname + ' [' + ip + ']')
    else:
        doc += kml.tagged_text ('name', ip)

    doc += kml.empty_tag ('Snippet maxLines="0"')

    doc += kml.tag ('description')

    doc += kml.text ('<![CDATA[')
#    doc += kml.text ('??NsaSentence')
#    doc += kml.text ('??NsaSrc')

    # print '\n\n\n\nhop_properties: ' , hop_properties

    # --- Noticed some HTML errors here; since HTML errors can cause
    #     weird problems (possibly the Google-freeze) I've converted
    #     this from HTML strings to using the xml_utils class ---

    cdata = xml_utils (initial_indent = kml.get_indent_level()+1 )
    
    doc += cdata.tag ('font size="4"')
    doc += cdata.tagged_text ('b', ip_info['city'])
    doc += cdata.empty_tag ('br')
    doc += cdata.text (ip_info['region'] + ', ' + ip_info['country'])
    doc += cdata.end_tag ('/font')
    doc += cdata.empty_tag ('br')
    doc += cdata.empty_tag ('br')

    if ip_info['hostname'] != ip_info['ip_addr']:
        doc += cdata.tagged_text ('a href="http://ixmaps.ischool.utoronto.ca/faq.html#IPAddress"', 'ip:')
        doc += cdata.text_cont_line (ip_info['ip_addr'])
        doc += cdata.empty_tag ('br')
        doc += cdata.tagged_text ('a href="http://ixmaps.ischool.utoronto.ca/faq.html#Hostname"', 'hostname:')
        doc += cdata.text_cont_line (ip_info['hostname'])
        doc += cdata.empty_tag ('br')
        # doc += kml.text_cont_line ('name/ip/as/ms: '
                         # + ip_info['hostname'] + ' / '
                         # + ip_info['ip_addr'] + ' / '
                         # + ip_info['asnum'] + ' / ' )
    else:
        doc += cdata.tagged_text ('a href="http://ixmaps.ischool.utoronto.ca/faq.html#IPAddress"', 'ip:')
        doc += cdata.text_cont_line (ip_info['ip_addr'])
        doc += cdata.empty_tag ('br')

    doc += cdata.tagged_text ('a href="http://ixmaps.ischool.utoronto.ca/faq.html#ASNumber"', 'AS:')
    doc += cdata.text_cont_line (ip_info['asnum'])
    doc += cdata.empty_tag ('br')
    doc += cdata.text_cont_line ('lat: ' + ip_info['lat'] + ', long: ' + ip_info['long'])
    doc += cdata.empty_tag ('br')
    doc += cdata.tagged_text ('a href="http://ixmaps.ischool.utoronto.ca/technical.html"', 'geoprecision:')
    doc += cdata.text_cont_line (ip_info['geo_precision'])
    doc += cdata.empty_tag ('br')
    doc += cdata.empty_tag ('br')
    doc += cdata.tagged_text ('a href="http://ixmaps.ischool.utoronto.ca/faq.html#Hop"', 'hop:')
    doc += cdata.text_cont_line (hop)
    doc += cdata.empty_tag ('br')

    doc += kml.text (']]>')

    doc += kml.end_tag ('/description')

    doc += kml.tagged_text ('styleUrl', '#' + hop_style) 

    # doc += kml.tagged_text ('altitudeMode', 'relativeToGround')
    doc += kml.tag ('Point')
    doc += kml.tagged_text ('coordinates', str(hop_properties['long']) +
                            ',' + str(hop_properties['lat']) + ',0')
    doc += kml.end_tag ('/Point')
    doc += kml.end_tag ('/Placemark')

    return doc

def kml_placemark_line (route_id, route_hops):
    kml = xml_utils()
    doc = kml.text()

    # route_id = int(route_hop_attempts[0]['traceroute_id'])

    # number_of_hops = get_available_hops (route_hop_attempts)
    number_of_hops = len (route_hops)

    # --- Display function name ---
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')

    # doc += 'route_id: ' + str(route_id) + '\n'
    # doc += 'route_hops: ' + str(route_hops) + '\n'

    doc += kml.tag ('Placemark id="placemark_line_' + str(route_id) + '"')

    doc += kml.tagged_text ('name', str(number_of_hops) + ' hops')
    doc += kml.tagged_text ('styleUrl', '#trPathStyle')

    doc += kml.tag ('LineString')
    doc += kml.tagged_text ('tessellate', 1)
    # doc += kml.tagged_text ('altitudeMode', 'relativeToGround')

    doc += kml.tag ('coordinates')
    doc += kml.text (get_coord_string(route_hops) )
    doc += kml.end_tag ('/coordinates')

    doc += kml.end_tag ('/LineString')
    
    doc += kml.end_tag ('/Placemark')

    return doc

# Todo: this function should take multiple ch's
def kml_chotel_style (ch):
    kml = xml_utils ( )
    doc = kml.text ( )

    ch['ixclass'] = get_ch_class (ch)

    facility = ''
    if ch['facility']:
        facility = "<p>%s</p>" % (ch['facility'] )

    # --- Display function name ---
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')

    # --- Create the unique highlighted style (ie with a
    #     building-photo) for this facility                ---
    doc += kml.tag ('Style id="ch_' + str(ch['id']) + '_sel"')
    doc += kml.tag ('IconStyle')
    doc += kml.tagged_text ('scale', 1.6)
    doc += kml.tag ('Icon')
    doc += kml.tagged_text ('href', ch['image_esc'])
    doc += kml.end_tag ('/Icon')
    doc += kml.end_tag ('/IconStyle')
    doc += kml.tag ('LabelStyle')
    doc += kml.tagged_text ('scale', 1.2)
    doc += kml.end_tag ('/LabelStyle')
    doc += kml.tag ('BalloonStyle')
    doc += kml.tag ('text')
    doc += kml.cdata ('''<table border="0" width="305" cellspacing="0" cellpadding="0">
  <tr align="left" valign="top">
    <td width="100%" align="left" valign="top">
      <p>
        <a href=\"''' + ixmaps.URL_HOME + '''\"; title="IXmaps">
          <img src=\"''' + ixmaps.URL_HOME + '''ge/ixmaps.png\" alt="" width="270" height="60"/>
        </a>
      </p>''' + facility + '''
      <p>
        <strong>$[name]</strong>
      </p>
      $[description]
    </td>
  </tr>
</table>''')
    doc += kml.end_tag ('/text')
    doc += kml.end_tag ('/BalloonStyle')
    doc += kml.end_tag ('/Style')    

    doc += kml.text ( )
    doc += kml.tag ('StyleMap id="ch_' + str(ch['id']) + '"')
    doc += kml.tag ('Pair')
    doc += kml.tagged_text ('key', 'normal')
    doc += kml.tagged_text ('styleUrl', '#' + ch['ixclass'] + '_nonsel')
    doc += kml.end_tag ('/Pair')

    doc += kml.tag ('Pair')
    doc += kml.tagged_text ('key', 'highlight')

    # --- Highlighted image contains the building photo (if it exists) ---
    if ch['image_esc']:
        doc += kml.tagged_text ('styleUrl', '#ch_' + str(ch['id']) + '_sel')
    # --- Else use the generic image for facility-type ---
    else:
        doc += kml.tagged_text ('styleUrl', '#' + ch['ixclass'] + '_sel')
        
    doc += kml.end_tag ('/Pair')

    doc += kml.end_tag ('/StyleMap')

    return doc

def kml_chotel_placemarks (chotel, is_visible=1, add_to_id=''):
    kml = xml_utils()
    doc = kml.text()
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')
    
    # print '\n\nchotel["id"]'
    # print chotel

    doc += kml.tag ('Placemark id="ch_hop_' + str(chotel['id'])
                    + add_to_id + '"')

    doc += kml.tagged_text ('name', chotel['address'] )
    doc += kml.tagged_text ('visibility', is_visible)
    doc += kml.empty_tag ('Snippet maxLines="0"')
    doc += kml.tag ('description')

#why is this pulling from the main DB? Why is ch_operator and ch_build_owner equal 'None' string instead of null?
#Are there cases of null (cause they are not errorchecked here)
    doc += kml.text ('<![CDATA[')
#    doc += kml.text ('??nsa_sentence ??nsa_src')

#does the following line do anything?
    doc += kml.text ('<!-- <b>' + chotel['address'] + '</b><br/><br/> -->')
    if str(chotel['ch_operator']) != 'None' and str(chotel['ch_operator']) != '':
        doc += kml.text ('Operator: <a href=' + chotel['ch_operator_src'] + '>' + str(chotel['ch_operator']) + '</a><br/>')
    if str(chotel['ch_build_owner']) != 'None' and str(chotel['ch_build_owner']) != '' and str(chotel['ch_build_owner_src']) != '':
        doc += kml.text ('Building owner: <a href=' + chotel['ch_build_owner_src'] + '>' + str(chotel['ch_build_owner']) + '</a><br/>')
    elif str(chotel['ch_build_owner']) != 'None' and str(chotel['ch_build_owner']) != '':
        doc += kml.text ('Building owner: ' + str(chotel['ch_build_owner']) + '<br/>')
    if 'networks' in chotel:
        doc += kml.text ('Networks: <a href=' + chotel['isp_src'] + '>' + chotel['networks'] + '</a><br/>')
    doc += kml.text ('lat: ' + str(chotel['lat']) + ', long: ' + str(chotel['long']) + '<br/>')
    if (chotel['image'] ):
        doc += kml.text ('<img src="' + chotel ['image'] + '"/><br/>')
    doc += kml.text (']]>')

    doc += kml.end_tag ('/description')

    doc += kml.tagged_text ('styleUrl', '#ch_' + str(chotel['id'] ) )
    doc += kml.tag ('Point')
    doc += kml.tag ('coordinates')
    doc += kml.text (str(chotel['long']) + ',' + str(chotel['lat']) + ',0')
    doc += kml.end_tag ('/coordinates')
    doc += kml.end_tag ('/Point')
    doc += kml.end_tag ('/Placemark')

    return doc

def kml_chotel_layers (chotel_obj, visible_layers=None):
    kml = xml_utils ( )
    doc = kml.text ( )
    doc += kml.comment (sys._getframe().f_code.co_name + ' ( )')

    all_chotels = chotel_obj.get_all ( )
    ch_chotels = chotel_obj.get_type ('CH')
    nsa_chotels = chotel_obj.get_type ('NSA')
    google_chotels = chotel_obj.get_type ('Google')
    uc_chotels = chotel_obj.get_type ('UC')

    # --- Create any undefined layers ---
    if not visible_layers:
        visible_layers = {}
    if 'chotel' not in visible_layers:
        visible_layers['chotel'] = 0
    if 'nsa' not in visible_layers:
        visible_layers['nsa'] = 0
    if 'google' not in visible_layers:
        visible_layers['google'] = 0
    if 'uc' not in visible_layers:
        visible_layers['uc'] = 0

    doc +=  kml.tag ("Folder")
    doc +=  kml.tagged_text ('name', 'Carrier hotels')
    doc +=  kml.tagged_text ('visibility', visible_layers['chotel'])
    doc +=  kml.tagged_text ('styleUrl', '#ixFolderStyle')
    for ch in ch_chotels:
        doc +=  kml.indent (kml_chotel_placemarks (ch, visible_layers['chotel']) )

    doc +=  kml.end_tag ("/Folder")

    doc +=  kml.tag ("Folder")
    doc +=  kml.tagged_text ('name', 'NSA')
    doc +=  kml.tagged_text ('visibility', visible_layers['nsa'])
    doc +=  kml.tagged_text ('styleUrl', '#ixFolderStyle')
    for ch in nsa_chotels:
        doc +=  kml.indent (kml_chotel_placemarks (ch, visible_layers['nsa']) )

    doc +=  kml.end_tag ("/Folder")

    doc +=  kml.tag ("Folder")
    doc +=  kml.tagged_text ('name', 'Google data centres')
    doc +=  kml.tagged_text ('visibility', visible_layers['google'])
    doc +=  kml.tagged_text ('styleUrl', '#ixFolderStyle')
    for ch in google_chotels:
        doc +=  kml.indent (kml_chotel_placemarks (ch, visible_layers['google']) )

    doc +=  kml.end_tag ("/Folder")

    doc +=  kml.tag ("Folder")
    doc +=  kml.tagged_text ('name', 'Undersea cable landing site')
    doc +=  kml.tagged_text ('visibility', visible_layers['uc'])
    doc +=  kml.tagged_text ('styleUrl', '#ixFolderStyle')
    for ch in uc_chotels:
        doc +=  kml.indent (kml_chotel_placemarks (ch, visible_layers['uc']) )

    doc +=  kml.end_tag ("/Folder")

    return doc

def get_coord_string2 (route_hop_attempts, conn):
    nhops = get_available_hops(route_hop_attempts)
    addrs = get_available_ip_addrs(route_hop_attempts, nhops)
    coords = ''
    count_coords = 0
    for i in range(len(addrs)):
        addr = addrs[i]
        ai = ixmaps.get_ip_addr_info(conn, addr)
        longitude = ai['long']
        latitude =  ai['lat']

        if len(longitude) > 0 and len(latitude) > 0:
            if is_valid_coord(longitude, latitude):
                coords += longitude+','+latitude+',0\n'
                count_coords += 1

    return coords

def get_coord_string (coords_list):
    coords_string = ''
    for coords in coords_list:
        longitude = coords['long']
        latitude =  coords['lat']

        # if len(longitude) > 0 and len(latitude) > 0:
        if (longitude != None) and (latitude != None):
            if is_valid_coord(longitude, latitude):
                coords_string += longitude+','+latitude+',0\n'

    return coords_string

def get_route_hops (route_hop_attempts, conn):
    # print ("route_hop_attempts:", len(route_hop_attempts))
    nhops = get_available_hops(route_hop_attempts)
    ip_list = ixmaps.get_available_ip_addresses(route_hop_attempts)

    coords = [] # [{}] * ( route_hop_attempts [ len(route_hop_attempts) - 1] ['hop'] ) 
    # print 'len(coords):', len(coords)

    

    # --- Get route-info on each hop ---
    for i in range(len(ip_list)):
        addr = ip_list[i]
        ip_addr_info = ixmaps.get_ip_addr_info(conn, addr)

        # if ip_addr_info['lat'] == None:
            # ip_addr_info['lat'] = ip_addr_info['mm_lat']
            # ip_addr_info['long'] = ip_addr_info['mm_long']

        coords.append (ip_addr_info)
        if len(ip_addr_info['long']) != 0 or len(ip_addr_info['lat']) != 0:
            if (not is_valid_coord(ip_addr_info['long'], ip_addr_info['lat'])):
                ip_addr_info['long'] = None
                ip_addr_info['lat'] = None

    last_hop = 0

    # --- 
    for i in range(len(route_hop_attempts) ):
        hop_attempt = route_hop_attempts[i]
        # print '\n\n\n\nhop_attempt (i):' , i
        # print hop_attempt

        hop = hop_attempt['hop']
        if (hop != last_hop):
            # print "\n\n\n\nhop-1:", hop-1
            # print "len(coords)", len(coords)
            # print ("len(route_hop_attempts):", len(route_hop_attempts),
                   # ", i:", i)
            # print hop_attempt
            coords[hop-1]['rtt'] = []
            last_hop = hop

        attempt = hop_attempt['attempt']
        # print "len: ", coords[hop-1]['rtt_ms'], attempt
        # if (coords[hop-1]['rrt_ms'] <= attempt):
        coords[hop-1]['rtt'].insert(len(coords[hop-1]['rtt']),
                                    hop_attempt['rtt_ms'] )

        # print "coords:", coords
        # -- IPs must be strings ---
        for hop in coords:
            # print "hop: ", hop
            if hop['ip_addr'] == None:
                hop['ip_addr'] = ''

    return coords

def get_coord_count (conn, traceroute):
    tr_body = ixmaps.get_tr_items (conn, traceroute)
    nhops = get_available_hops(tr_body)
    addrs = get_available_ip_addrs(tr_body, nhops)
    coords = ''
    count_coords = 0
    for i in range(len(addrs)):
        addr = addrs[i]
        ai = ixmaps.get_ip_addr_info(conn, addr)
        longitude = ai['long']
        latitude =  ai['lat']

        if len(longitude) > 0 and len(latitude) > 0:
            if is_valid_coord(longitude, latitude):
                coords += longitude+','+latitude+',0\n'
                count_coords += 1

    return count_coords

def get_ip (traceroute, hop):
    tr_body = ixmaps.get_tr_items (conn, traceroute)
    nhops = get_available_hops(tr_body)
    addrs = get_available_ip_addrs(tr_body, nhops)
    addr = addrs[hop]
    # hdesc = ixmaps.get_ip_addr_info (conn, addr)

    return addr

    # coords = ''
    # count_coords = 0


    # hdesc = {}
    # hdesc['ip'] = addr
    # hdesc['lat'] = addr
    # hdesc['long'] = addr
    # hdesc['hop'] = addr
    # hdesc['country'] = addr
    # hdesc['region'] = addr
    # hdesc['city'] = addr

    # return hdesc

def get_conn ( ):
    return ixmaps.DBConnect.getConnection ( )

def get_available_hops(da):
    hop = -1
 
    for d in da:
        try:
            if d['hop'] > hop:
                hop = d['hop'] 
        except KeyError:
            pass
    return hop
	
def is_valid_ip (ip): 
    if not ip:
        ip = ''
    if (re.match (r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s*$', ip) ):
        return True
    else:
        return False    

def get_available_ip_addrs(da, nhops):
    aa = [None] * nhops
    for d in da:
        try:
            hop = d['hop']
            addr = d['ip_addr']
            aa[hop-1] = addr
        except IndexError:
            pass
        except KeyError:
            pass
    return aa 

def get_rtts(da, hop, attempts):
    """get Round Trip Times from a traceroute body.
       
       da is an array of dictionaries, each dictionary holding
          the result from a single probe packet.
       hop is the hop number we're looking for, starting at 1
       attempts is the number of attempts made for each hop
    """
    rtts = [None] * attempts
    for d in da:
        try:
            if d['hop'] == hop:
                attempt = d['attempt']-1
                rtts[attempt] = d['rtt_ms']
        except IndexError:
            pass
        except KeyError:
            pass
    return rtts

def within(point1, point2, dist):
    dx = point2[0] - point1[0]
    dy = point2[1] - point1[1]
    dist_squared = dx*dx + dy*dy
    return dist_squared < dist*dist

def is_valid_coord(longitude, latitude):
    """Reject invalid coordinates too close to "placeholder" coordinates.
    
    These are: 0,0  in Atlantic off of Africa
               -95,60  near shore of Hudson's Bay, used by MaxMind for unknown in Canada
               -97.38  a field in Kansas, used by MaxMind for unknown in US"""

    if ((longitude == None)
    or (longitude == '')
    or (latitude == None)
    or (latitude == '')):
        return False

    bad_coords = [(0.0,0.0), (-95.0,60.0), (-97.0,38.0)]
    point2=(float(longitude), float(latitude))
    for c in bad_coords:
        if within(c, point2, 0.0001):
            return False
    return True

def main (traceroute_id_list, visible_layers=None, commandline_mode=False ):

    conn = ixmaps.DBConnect.getConnection ( )

    fac_icons = facility_icons ( )

    chotel_obj = CHotels (conn)
    all_chotels = chotel_obj.get_all ( )

    kml = xml_utils()

    traceroute_items_dict = {}
    hostnames = {}
    for route_id in traceroute_id_list:
        
        traceroute_items_dict[str(route_id)] = ixmaps.get_tr_items(conn,route_id)
    if not commandline_mode:
        print get_http_header ( )

    print (xml_document_header ( ) ),

    print kml.tag ('kml xmlns="http://www.opengis.net/kml/2.2"'),
    print kml.tag ("Document"),

    print kml.indent(kml_doc_setup ( ) ),

    # --- General styles for the various facilities ---
    for icon in fac_icons:
        print kml.indent (kml_hop_style (fac_icons[icon] ) ),

    # --- Create specific styles for each facility ---
    for ch in all_chotels:
        print  kml.indent (kml_chotel_style (ch) ),

    print kml.indent(kml_legend ( ) ),

    # --- Render traceroutes ---
    for traceroute in traceroute_id_list:
        print kml.text (kml_traceroute (traceroute, chotel_obj, conn) ),
        
    print kml.indent (kml_chotel_layers (chotel_obj, visible_layers) ),
    print kml.end_tag ("/Document"),
    print kml.end_tag ("/kml"),








# --- Get user arguments, and call main ( ) ---
if __name__ == "__main__":
    traceroute_id_strings = []
    is_this_commandline = False
    visible_layers = {}

    # --- try the command-line args ---
    for arg in sys.argv[1:]:

        # -- Note that we're in command-line mode --
        is_this_commandline = True

        # -- Get traceroute strings --
        traceroute_id_strings.append (arg)

        # -- Load extra layers --
        visible_layers['nsa'] =    0
        visible_layers['chotel'] = 0
        visible_layers['google'] = 0
        visible_layers['uc'] =     0

    # --- If we're not in the commandline, check if you can read the
    #     (web) form ---
    if not is_this_commandline:
        is_this_commandline = False

        # -- Get CGI variables --
        form = cgi.FieldStorage()
        traceroute_id_strings = form.getlist("traceroute_id")
        is_nsa_vis = form.getfirst("show_nsa_listening_posts")
        is_chotel_vis = form.getfirst ('show_chotel')
        is_google_vis = form.getfirst ('show_google')
        is_uc_vis = form.getfirst ('show_landing_sites')

        # --- Convert CGI strings into binary ---
        visible_layers['chotel'] = 1 if (is_chotel_vis=='true') else 0
        visible_layers['nsa'] =    1 if (is_nsa_vis=='true')    else 0
        visible_layers['google'] = 1 if (is_google_vis=='true') else 0
        visible_layers['uc'] =     1 if (is_uc_vis=='true')     else 0
        
    if not visible_layers:
        visible_layers = { }

    traceroute_id_list = [ ]
    for trid in traceroute_id_strings:
        traceroute_id_list.append (int(trid))

    main(traceroute_id_list, visible_layers,
         commandline_mode=is_this_commandline)

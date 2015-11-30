#!/usr/bin/python

"""
Render a traceroute for display by Google Earth.
"""
DEBUG=False
#FIXME  errors should never give a 2xx response
#FIXME  program need a major re-write 
#FIXME  generate hop-styles on the fly

import pg
import time
import cgi
import math
import string
import cgitb; cgitb.enable()
import sys
import re
import ixmaps
import ixmaps2_tmp
from cStringIO import StringIO


# persuant to OPEN DATA LICENSE (GeoLite Country and GeoLite City databases)
MAX_MIND_ATTRIBUTION="""
  <br/><br/>
This product includes GeoLite data created by MaxMind, available from
<a href="http://maxmind.com/">http://maxmind.com/</a>
"""

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

EARTH_EQUAT_RADIUS = 6378.145    # Equatorial radius in km
EARTH_FLAT = 1.0/298.0           # ellipsoidal flattening at the poles
EARTH_MEAN_RADIUS = EARTH_EQUAT_RADIUS * (1.0 - 0.5*EARTH_FLAT)

URL_HOME = "http://dev.ixmaps.ischool.utoronto.ca/"
# URL_HOME = "http://www.ixmaps.ca/"
# URL_HOME = "http://test.n-space.org/ixmaps/"

RE_NOTEMPTYLINE = re.compile(r"^(?!$)", re.MULTILINE)
RE_XMLTAG = re.compile(r"^([a-z0-9_]+).*", re.IGNORECASE + re.DOTALL)

def ll_to_xyz(lat, long):
    lat_radians = math.pi * lat / 180.0
    long_radians = math.pi * long / 180.0
    x = EARTH_MEAN_RADIUS * math.cos(long_radians) * math.cos(lat_radians)
    y = EARTH_MEAN_RADIUS * math.sin(long_radians) * math.cos(lat_radians)
    z = EARTH_MEAN_RADIUS * math.sin(lat_radians)
    return (x,y,z)

def km_to_degrees(km, lat, scale=1.0):
    deg_lat = scale*km*180.0/(EARTH_MEAN_RADIUS*math.pi)
    deg_long = deg_lat / math.cos(math.pi*lat/180.0)
    return (deg_lat, deg_long)

def distance_km(pos1, pos2):
    dx = pos2[0]-pos1[0]
    dy = pos2[1]-pos1[1]
    dz = pos2[2]-pos1[2]
    return math.sqrt(dx*dx+dy*dy+dz*dz)

def ll_line_to_km (ll1, ll2):
    pos1 = ll_to_xyz (ll1[0], ll1[1])
    pos2 = ll_to_xyz (ll2[0], ll2[1])
    return distance_km (pos1, pos2)

MILE_TO_KM = 1.609344

# MAX_CHOTEL_DIST = EARTH_EQUAT_RADIUS * 2
MAX_CHOTEL_DIST = 0.05*MILE_TO_KM
# MAX_CHOTEL_DIST = 10.0*MILE_TO_KM

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


class TracerouteException(Exception):
    pass

class DBConnect(object):
    conn = None
    def getConnection():
        if not DBConnect.conn:
            DBConnect.conn = pg.connect("ixmaps", "localhost", 5432)
        return DBConnect.conn
    getConnection = staticmethod(getConnection)

class xml_utils:
    def __init__ (self, initial_indent=0):
        self.stack = []
        self.endline = "\n"
        self.initial_indent = initial_indent

    def tag(self, tag_plus_attr):
        if tag_plus_attr[0] == "/":
            raise ValueError
        
        full_tag = self.indent("<" + tag_plus_attr + ">")
        tag = re.sub (RE_XMLTAG, r"\1", tag_plus_attr)

        # if re.match ('Placemark', tag):
        # print "(" + str(tag) + ", " + str(self.stack_size()) + ", " + str(self.stack) + ")"

        self.stack.append (str(tag))
        return full_tag + self.endline

    def empty_tag (self, tag_plus_attr):
        if tag_plus_attr[0] == "/":
            raise ValueError
        full_tag = self.indent ("<" + tag_plus_attr + " />" ) 
        return full_tag + self.endline

    def end_tag(self, tag=None):
        item = self.stack[-1]
        if (tag):
            if (tag[0] == "/"):
                tag = tag[1:]

        # print "(/" + str(tag) + ", " + str(self.stack_size()) + ", " + str(self.stack) + ")"

        if ((tag != None) and (item != tag)):
            raise ValueError

        else:
            self.stack.pop()
            return self.indent("</" + item + ">") + self.endline

    def stack_size(self):
        return (len (self.stack))

    def get_indent_level (self):
        return self.stack_size ( ) + self.initial_indent

    def indent (self, text, extra=0):
        text = str(text)

        ind = self.stack_size()
        indent_increment = "  " 

        new_text = re.sub (RE_NOTEMPTYLINE, indent_increment * (ind+extra+self.initial_indent), text)
        return new_text

    def text (self, text=""):
        if (text != '' and text != None):
            return self.indent (text) + self.endline
        else:
            return self.endline

    def text_cont_line (self, text):
        if (text != '' and text != None):
            return self.indent (text) 
        else:
            return ''

    def tagged_text (self, tag_plus_attr, text):
        text = str(text)
        full_tag = self.indent("<" + tag_plus_attr + ">")
        end_tag = "</" + re.sub (RE_XMLTAG, r"\1", tag_plus_attr) + ">"
        return full_tag + text + end_tag + self.endline

    def comment (self, comment_tag):
        full_tag = "<!-- " + comment_tag + " -->" 
        return self.indent (full_tag) + self.endline

    def cdata (self, text):
        full_text = (self.indent ("<![CDATA[") 
        + "\n"
        + self.indent (text, extra=1) + "\n" 
        + self.indent ("]]>"))

        return full_text + self.endline

def indent_level (text, indent=0):
    indent_increment = "  " 
    new_text = re.sub (RE_NOTEMPTYLINE, indent_increment * indent, text)
    return new_text

def get_http_header (traceroute_id=None):
    if traceroute_id:
        ret = 'Content-Disposition: inline; filename="IXmaps_GE%d.kml"\n' % traceroute_id[idlist]
    else:
        ret = 'Content-Disposition: inline; filename="IXmaps_GE.kml"\n'
    ret += "Content-Type: application/vnd.google-earth.kml+xml; charset=UTF-8"
    ret += "\n"

    return ret

def get_traceroute(conn, id):
    qres = conn.query("select * from traceroute where id=%d" % id)
    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise TracerouteException, "failed to find traceroute %d" % id
    return qres.dictresult()[0]


def get_tr_items (conn, id):
    return get_traceroute_items_db (conn, id)

def get_traceroute_items_db (conn, id):
    qres = conn.query ("select * from tr_item where traceroute_id=%d order by hop, attempt" % id)
    try:
        id = qres.dictresult()[0]['traceroute_id']
    except IndexError:
        raise TracerouteException, "failed to find traceroute items for %d" % id
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

def get_ip_addr_info (conn, addr):
    # print "IP: " + str(addr)

    if addr:
        # print "addr: " + str(addr)
        qres = conn.query("select * from ip_addr_info where ip_addr='%s'" % addr)
        d = qres.dictresult()[0]
        d['ip_addr'] = addr
        d['hostname'] = str(d['hostname'])
        d['lat'] = str(d['lat'])
        d['long'] = str(d['long'])
        d['asnum'] = str(d['asnum'])
        d['country'] = str(d['mm_country'])
        d['region'] = str(d['mm_region'])
        d['city'] = str(d['mm_city'])
        d['pcode'] = str(d['mm_postal'])
        d['area_code'] = str(d['mm_area_code'])
        d['dma_code'] = str(d['mm_dma_code'])
        d['override'] = str(d['gl_override'])

    else:
        d={'lat': '', 'hostname': '', 'ip_addr': None, 'long': '', 'asnum': '',
           'region': '', 'city': '', 'country': '', 'pcode': '', 'area_code': '', 'dma_code': '', 'override': ''}
        
    return d

def get_ip_info (conn, ip_list):
    # print "IP: " + str(addr)

    addr = ''
    for address in ip_list:
        if address:
            addr += "ip_addr='" + address + "' "

    addr = re.sub (r"(\.[0-9]+') (ip_addr=')", r'\1 or \2', addr)
    addr = '(' + addr + ')'

    # print "addr: " + str(addr)
    qres = conn.query("select * from ip_addr_info where %s" % addr)

    ip_details = qres.dictresult()

    ip_dict = {}

    for d in ip_details:
        # d['ip_addr'] = addr

        ip = d['ip_addr']

        ip_dict[ip] = {}

        ip_dict[ip]['ip_addr'] = ip
        ip_dict[ip]['hostname'] = str(d['hostname'])
        ip_dict[ip]['lat'] = str(d['lat'])
        ip_dict[ip]['long'] = str(d['long'])
        ip_dict[ip]['asnum'] = str(d['asnum'])
        ip_dict[ip]['country'] = str(d['mm_country'])
        ip_dict[ip]['region'] = str(d['mm_region'])
        ip_dict[ip]['city'] = str(d['mm_city'])
        ip_dict[ip]['pcode'] = str(d['mm_postal'])
        ip_dict[ip]['area_code'] = str(d['mm_area_code'])
        ip_dict[ip]['dma_code'] = str(d['mm_dma_code'])
        ip_dict[ip]['override'] = str(d['gl_override'])

        if ip_dict[ip]['override']:

            #this is a little different than tr-detail, maybe FIX?
            lat_digits = len(str(d['lat'])) - str(d['lat']).find('.') - 1
            long_digits = len(str(d['long'])) - str(d['long']).find('.') - 1
            if lat_digits >= 5 or long_digits >= 5:
                ip_dict[ip]['geo_precision'] = 'building level'
            elif lat_digits <= 2 or long_digits <= 2:
                ip_dict[ip]['geo_precision'] = 'city level'
            else:
                ip_dict[ip]['geo_precision'] = 'Maxmind'
        
    return ip_dict

def get_complete_traceroute(conn, traceroute_id):
    tr_header = get_traceroute(conn, traceroute_id)
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
    return (tr_header, tr_body, nhops, nattempts, rtt, ipaddrs)

def is_accurate_to (places, x):
    X = x * math.pow (10, places)
    if (int(X) % 10) != 0:
        return True
    else:
        return False
    

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

def get_ch_networks(conn, ch):
    if not ch.has_key('networks'):
        qres = conn.query("select name from chnetwork join ch_networks on net_id = chnetwork.id where ch_id=%d" % ch['id'])
        ch['networks'] = ','.join([d['name'] for d in qres.dictresult()])

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
        
# Todo: remove CHotels object, replace with a couple of chotel-functions

class CHotels(object):
    def __init__(self, conn):
        qres = conn.query("select * from chotel")
        try:
            id = qres.dictresult()[0]['id']
        except IndexError:
            raise TracerouteException, "failed to find any carrier hotels"
        chotels = qres.dictresult()
        location_styles = facility_icons()
        for ch in chotels:
            ch['xyz'] = ll_to_xyz(ch['lat'], ch['long'])
            ch['to_render'] = False
            ixclass = get_ch_class(ch)
            ch['ixclass'] = string.replace(ixclass, "near", "", 1)
            ch['facility'] = location_styles[ch['ixclass']]['facility']
            ch['image_esc'] = URL_encode_ampersands(ch['image']) if (ch['image']) else ''
        self.chotels = chotels
        self.reset()

    def reset(self):
        self.index = 0

    def __iter__(self):
        return self

    def next(self):
        try:
            chotels = self.chotels
            index = self.index
            while not chotels[index]['to_render']:
                index += 1
            item = chotels[index]
            index += 1
            self.index = index
            return item
        except IndexError:
            raise StopIteration

    def nearest(self, longitude, latitude, km_radius=EARTH_EQUAT_RADIUS*2):
        """Find the nearest carrier hotel that's within a given radius in km."""
        point = ll_to_xyz(latitude, longitude)
        max_dist = km_radius
        chotel = None
        for ch in self.chotels:
            dist = distance_km(point, ch['xyz'])
            if dist < max_dist:
                #print ch['id'], ch['long'], ch['lat'], dist, max_dist
                max_dist = dist
                chotel = ch
        return chotel
        
    def all_within_by_id (self, longitude, latitude, km_radius=EARTH_EQUAT_RADIUS*2):
        chotel_list = self.all_within (longitude, latitude, km_radius)

        chotel_dict = {}
        for chotel in chotel_list:
            chotel_dict[chotel['id']] = chotel

        return chotel_dict

    def all_within (self, longitude, latitude, km_radius=EARTH_EQUAT_RADIUS*2, set_to_render=False):
        """Create a list of carrier hotels within a given radius in km."""
        point = ll_to_xyz(latitude, longitude)
        chotel = None
        chotel_tuple_list = [ ]

        # --- Create list of chotels within radius ---
        for ch in self.chotels:
            dist = distance_km (point, ch['xyz'] )
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
                ch['to_render'] = True

        # print chotel_list

        return chotel_list

    def nsa (self, set_to_render=False):
        """Get the NSA listening posts."""
        chotel_list = []
        for ch in self.chotels:
            if ch['nsa']:
                chotel_list.append(ch)

        for ch in chotel_list:
            if set_to_render:
                ch['networks'] = ''
                ch['to_render'] = True

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
    'NSA1'        : { 'id': 'NSA1',        'symbol': 'nsahigh',          'facility': '<b>Known NSA listening post</b> located at' },
    'NSA2'        : { 'id': 'NSA2',        'symbol': 'nsamedium',        'facility': '<b>Likely NSA listening post</b> located in' },
    'NSA3'        : { 'id': 'NSA3',        'symbol': 'nsalow',           'facility': '<b>Possible NSA listening post</b> located in' },
    'CRG'         : { 'id': 'CRG',         'symbol': 'crg',              'facility': 'Owned by Carlyle Real Estate - CoreSite' },
    'nearCRG'     : { 'id': 'nearCRG',     'symbol': 'nearcrg',          'facility': 'Near a facility owned by Carlyle Real Estate - CoreSite' },
    'INT'         : { 'id': 'INT',         'symbol': 'locationcircle',   'facility': '<b>Router</b> located in' },
    'chotel'      : { 'id': 'chotel',      'symbol': 'carrierhotel',     'facility': '<b>Carrier hotel</b> located at' },
    'UC'          : { 'id': 'UC',          'symbol': 'undersea',         'facility': '<b>Undersea cable landing site</b> located in' },
    'OTH'         : { 'id': 'OTH',         'symbol': 'locationcircle',   'facility': 'Router' },  # other (is this ever used in the current setup?)
        }
    return icons

def get_ixclass (ip_list, hop):
    # ixclass = ['OTH'] * len (ip_list)
    pass

def kml_hop_style (style):

    kml = xml_utils()
    doc = kml.text()
    doc += kml.comment ('kml_hop_style ({' + str(style['id']) + '})')

    doc += kml.tag('Style id="' + style['id'] + '_nonsel"')
    doc += kml.tag('IconStyle')
    doc += kml.tagged_text ('scale', 0.8)
    doc += kml.tag ('Icon')
    doc += kml.tagged_text ('href', URL_HOME + '/ge/' + style['symbol'] + '.png')
    doc += kml.end_tag ('/Icon')
    doc += kml.end_tag ('/IconStyle')
    doc += kml.tag ('LabelStyle')
    doc += kml.tagged_text ('scale', 0.8)
    doc += kml.end_tag ('/LabelStyle')
    doc += kml.tag ('BalloonStyle')
    doc += kml.tag ('text')
    doc += kml.cdata ('''<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top">
    <td width="100%" align="left" valign="top">
      <p><a href=\"''' + URL_HOME + '''\"; title="IXmaps">
        <img src=\"''' + URL_HOME + '''ge/ixmaps.png\" alt="" width="270" height="60"></a></p>
      <p>''' + style['facility'] + '''</p> <p><strong>$[name]</strong></p>
      $[description]
    </td></tr></table>''')
    doc += kml.end_tag ('/text')
    doc += kml.end_tag ('/BalloonStyle')
    doc += kml.end_tag ("/Style")

    doc += kml.tag ('Style id="' + style['id'] + '_sel"')
    doc += kml.tag ('IconStyle')
    doc += kml.tagged_text ('scale', 0.9)
    doc += kml.tag ('Icon')
    doc += kml.tagged_text ('href', URL_HOME + 'ge/' + style['symbol'] + '.png')
    doc += kml.end_tag ('/Icon')
    doc += kml.end_tag ('/IconStyle')
    doc += kml.tag ('LabelStyle')
    doc += kml.tagged_text ('scale', 1.2)
    doc += kml.end_tag ('/LabelStyle')

    doc += kml.tag ('BalloonStyle')
    doc += kml.tag ('text')
    doc += kml.cdata ("""<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top">
    <td width="100%" align="left" valign="top">
      <p><a href=\"""" + URL_HOME + """\"; title="IXmaps"><img src=\"""" + URL_HOME + """ge/ixmaps.png\" alt="" width="270" height="60"></a></p>
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


def kml_instructions ():
    kml = xml_utils()
    doc = ''

    doc += kml.text()
    doc += kml.comment ('kml_instructions ( )')

    doc += kml.tag ("Document")
    doc += kml.tagged_text ('name', 'Instructions')
    doc += kml.tagged_text ('Snippet maxLines="0"', 'Instructions')

    doc += kml.tag ("description")

    doc += kml.cdata ('''<ul>
  <li>Click on icons to see locations of Carrier Hotels</li>
  <li>Click on location to see Carrier Hotel building</li>
  <li>Mouse over center of building to see infrastructure</li>
</ul>'''
    + MAX_MIND_ATTRIBUTION)

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
    route_hop_attempts = get_traceroute_items_db (conn, route_id) # aka tr_body

    # --- Each hop ---
    #     Note: route_hops needs to contain rtt-info
    #     Note2: you can probably remove conn from this func
    route_hops = get_route_hops (route_hop_attempts, conn)

    # --- A list of the IP addresses used in this route ---
    #     Note: this func should take route_hops rather than route_hop_attempts 
    #     Note2: This func should only have one of each ip.  
    ip_list = get_available_ip_addresses (route_hop_attempts) 

    # --- A dict containing the IP-address details ---
    ip_details = get_ip_info (conn, ip_list)

    dest_hostname = route_hops[len(route_hops)-1]['hostname']

    all_chotels = chotel_obj.get_all ( )

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
    doc += kml.tagged_text ('Snippet', len (route_hops) )
    
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

    # --- En-route carrier hotels layer ---
    for placemark in range (number_of_hops):
        ip = route_hops[placemark]['ip_addr']
        if ip:
            nearby_chotels =  chotel_obj.all_within_by_id(float(ip_details[ip]['long']),
                              float(ip_details[ip]['lat']),
                              MAX_CHOTEL_DIST)
            
            chotels_enroute = dict (chotels_enroute.items ( ) +
                                    nearby_chotels.items ( ) ) 

    doc +=  kml.tag ("Folder")
    doc +=  kml.tagged_text ('name', 'Carrier hotels en route')
    doc +=  kml.tagged_text ('visibility', 1)
    doc +=  kml.tagged_text ('styleUrl', '#ixFolderStyle')
    for chotel in chotels_enroute:
        doc += kml.indent (kml_chotel_placemarks (chotels_enroute[chotel],
                           add_to_id='_route_' + str(route_id) ) )
    doc += kml.end_tag ("/Folder")

    # --- Create the traceroute-line ---
    doc += kml.indent (kml_placemark_line (route_id, route_hops) )

    # --- Create the hop-placemarks (note: placemarks start from 0) ---
    for placemark in range (number_of_hops):

        ip = route_hops[placemark]['ip_addr']

        if ip:
            doc += kml.indent ( kml_placemark_hop (ip_details[ip],
                                                   route_id, placemark,
                                                   route_hops[placemark] ) )

    doc += kml.text ( )
    doc += kml.end_tag ("/Folder")

    return doc

def kml_placemark_hop (ip_info, route, hop, hop_properties):

    # print "iP: " + str(ip)
    ip = hop_properties['ip_addr']

    # ip_info = get_ip_addr_info (conn, ip)

    kml = xml_utils()
    doc = kml.text()
    doc += kml.comment ("kml_placemark_hop ( )")
    
    doc += kml.tag ('Placemark id="route_' + str(route) + '_hop_'
                    + str(hop) + '"')

#    doc += kml.tagged_text ('name', ip)

    # doc += kml.text (str(ip_info))

    doc += kml.empty_tag ('Snippet maxLines="0"')

    doc += kml.tag ('description')

    doc += kml.text ('<![CDATA[')
#    doc += kml.text ('??NsaSentence')
#    doc += kml.text ('??NsaSrc')

    # print '\n\n\n\nhop_properties: ' , hop_properties

# <<<<<<< Erik's variant
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

# >>>>>>> Colin's variant
    # doc += kml.text ('<font size = 4>')
    # doc += kml.text ('<b>' + ip_info['city'] + '</b><br/>')
    # doc += kml.text (ip_info['region'] + ', ' + ip_info['country'])
    # doc += kml.text ('</font>')
    # doc += kml.text ('<br/><br/>')
        
# ####### Ancestor
    # doc += kml.text ('<font size = 4>')
    # doc += kml.text ('<b>' + ip_info['city'] + '</b><br/>')
    # doc += kml.text (ip_info['region'] + ', ' + ip_info['country'])
    # doc += kml.text ('</font>')
    # doc += kml.text ('<br/><br/>')
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#Hop>hop</a>: ' + str(hop) + '<br/>')
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/technical.html>geoprecision</a>: ' + ip_info['geo_precision'] + '<br/>')
        
# ======= end
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

# <<<<<<< Erik's variant
    # doc += kml.text ('<font size = 4>')
    # doc += kml.text ('<b>' + ip_info['city'] + '</b><br/>')
    # doc += kml.text (ip_info['region'] + ', ' + ip_info['country'])
    # doc += kml.text ('</font>')
    # doc += kml.text ('<br/><br/>')
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#Hop>hop</a>: ' + str(hop) + '<br/>')
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/technical.html>geoprecision</a>: ' + ip_info['geo_precision'] + '<br/>')
        
    # if ip_info['hostname'] != ip_info['ip_addr']:
        # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#IPAddress>ip</a>: ' + ip_info['ip_addr'] + '<br/>')
        # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#Hostname>hostname</a>: ' + ip_info['hostname'] + '<br/>')
        # # doc += kml.text_cont_line ('name/ip/as/ms: '
                         # # + ip_info['hostname'] + ' / '
                         # # + ip_info['ip_addr'] + ' / '
                         # # + ip_info['asnum'] + ' / ' )
    # else:
        # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#IPAddress>ip</a>: ' + ip_info['ip_addr'] + '<br/>' )

    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#ASNumber>AS</a>: ' + ip_info['asnum'] + '</br>')
    # doc += kml.text ('lat: ' + ip_info['lat'] + ', long: ' + ip_info['long'] + '<br/>')
    # doc += kml.text (']]>')
# >>>>>>> Colin's variant
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#ASNumber>AS</a>: ' + ip_info['asnum'] + '</br>')
    # doc += kml.text ('lat: ' + ip_info['lat'] + ', long: ' + ip_info['long'] + '<br/>')
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/technical.html>geoprecision</a>: ' + ip_info['geo_precision'] + '<br/><br/>')
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#Hop>hop</a>: ' + str(hop) + '<br/>')
    # doc += kml.text (']]>')
# ####### Ancestor
    # doc += kml.text ('<a href=http://ixmaps.ischool.utoronto.ca/faq.html#ASNumber>AS</a>: ' + ip_info['asnum'] + '</br>')
    # doc += kml.text ('lat: ' + ip_info['lat'] + ', long: ' + ip_info['long'] + '<br/>')
    # doc += kml.text (']]>')
# ======= end

    doc += kml.end_tag ('/description')

    doc += kml.tagged_text ('styleUrl', '#INT')

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

    doc += kml.comment ("kml_placemark_line ( )")

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
        <a href=\"''' + URL_HOME + '''\"; title="IXmaps">
          <img src=\"''' + URL_HOME + '''ge/ixmaps.png\" alt="" width="270" height="60" />
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
    if ch['image_esc']:
        doc += kml.tagged_text ('styleUrl', '#ch_' + str(ch['id']) + '_sel')
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
        doc += kml.text ('<img src="' + chotel ['image'] + '" /><br/>')
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

def kml_nearby_chotel_layer (chotel_list):
    pass

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
        ai = get_ip_addr_info(conn, addr)
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
    ip_list = get_available_ip_addresses(route_hop_attempts)

    coords = [] # [{}] * ( route_hop_attempts [ len(route_hop_attempts) - 1] ['hop'] ) 
    # print 'len(coords):', len(coords)

    

    # --- Get route-info on each hop ---
    for i in range(len(ip_list)):
        addr = ip_list[i]
        ip_addr_info = get_ip_addr_info(conn, addr)

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
    tr_body = get_tr_items (conn, traceroute)
    nhops = get_available_hops(tr_body)
    addrs = get_available_ip_addrs(tr_body, nhops)
    coords = ''
    count_coords = 0
    for i in range(len(addrs)):
        addr = addrs[i]
        ai = get_ip_addr_info(conn, addr)
        longitude = ai['long']
        latitude =  ai['lat']

        if len(longitude) > 0 and len(latitude) > 0:
            if is_valid_coord(longitude, latitude):
                coords += longitude+','+latitude+',0\n'
                count_coords += 1

    return count_coords

def get_ip (traceroute, hop):
    tr_body = get_traceroute_items_db (conn, traceroute)
    nhops = get_available_hops(tr_body)
    addrs = get_available_ip_addrs(tr_body, nhops)
    addr = addrs[hop]
    # hdesc = get_ip_addr_info (conn, addr)

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
    return DBConnect.getConnection ( )

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

# ?? can this be part of get_route_hops()?

def get_available_ip_addresses (route_hop_attempts): 
    address_list = []
    last_successful_hop = 0

    # --- Save first successful attempt (of 4) for each hop ---
    for item in route_hop_attempts:
        if item['hop'] != last_successful_hop:
            hop = item['hop']
            addr = item['ip_addr']

            if (hop > len(address_list)):
                address_list.append (None)

            if is_valid_ip(addr):
                address_list[hop-1] = addr
                last_successful_hop = hop

    return address_list

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

def get_placemark_hop(hdesc):
    if DEBUG:
        print hdesc
        return

    # --- If keys don't exist then return ---
    if (not 'addr' in hdesc):
        return
    if hdesc['addr'] == hdesc['hostname']:
        hdesc['host_disp'] = hdesc['addr']
    else:
        hdesc['host_disp'] = "%s / %s" % (hdesc['hostname'], hdesc['addr'])
    # format the Round Trip Times
    rtts = ""
    for r in hdesc['rtts']:
        rtts += str(r)+','
    hdesc['rtts_disp'] = rtts[:-1]

    # # --- Determine whether this should have an image associated with it,
    #       or just a colour.  ---
    # if (hdesc['ch_id']):
        # urlStyle = "#ch_%(ch_id)s"
    # else:
        # urlStyle = "#%(ixclass)s"

    urlStyle = "#%(ixclass)s"


    nsa_sentence = ''
    nsa_src = ''

    if hdesc['nsa_src'] == "http://cryptome.org/klein-decl.htm": 
        nsa_src = hdesc['nsa_src'] + "<br /><br />"
        nsa_sentence = """According to AT&T network engineer Marc Klein,
        San Francisco, Seattle, San Jose, Los Angeles and San Diego
        have been identified as cities where AT&T installed NSA
        eavesdropping equipment.<br /><br />"""

    elif hdesc['nsa_src']:
        nsa_sentence += "The following source has identified this as a likely \
        location for NSA eavesdropping equipment:<br /><br />"
        nsa_src = hdesc['nsa_src'] + "<br /><br />"



    #FIXME: show pcode (if N.A.), area_code (if US), dma_code (if US)
    fmt_main = """   <Placemark id="hop_%(hop)d">
    <name>%(ixp)s</name>
    <Snippet maxLines="0"></Snippet>
    <styleUrl>""" + urlStyle + """</styleUrl>
    <Point>
        <coordinates>%(long)s,%(lat)s,0</coordinates>
    </Point>"""

    fmt_description = "        <![CDATA[" + \
    nsa_sentence + nsa_src + \
    """    name/ip/as/ms: %(host_disp)s AS%(asnum)s / %(rtts_disp)s ms<br/>
    lat: %(lat)s, long: %(long)s, hop: %(hop)d<br/>
    country: %(country)s<br/>
    region: %(region)s<br/>
    city: %(city)s<br/>"""

    if (hdesc['image']):
        fmt_image = """<img src="%(image)s" /> ]]>"""
    else:
        fmt_image = "]]>"

    fmt_footer = """    </Placemark>"""

    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()

    print fmt_main        % hdesc
    print "        <description>" ,
    print fmt_description % hdesc
    print fmt_image       % hdesc
    print "        </description>"
    print fmt_footer      % hdesc

    sys.stdout = old_stdout

    return mystdout.getvalue()

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

    # if (URL_HOME[-1] != '/'):
        # URL_HOME += '/'

    conn = DBConnect.getConnection ( )

    fac_icons = facility_icons ( )

    chotel_obj = CHotels (conn)
    all_chotels = chotel_obj.get_all ( )

    kml = xml_utils()

    traceroute_items_dict = {}
    hostnames = {}
    for route_id in traceroute_id_list:
        
        traceroute_items_dict[str(route_id)] = get_traceroute_items_db (conn, route_id)
    if not commandline_mode:
        print get_http_header ( )

    print (xml_document_header ( ) ),

    print kml.tag ('kml xmlns="http://www.opengis.net/kml/2.2"'),
    print kml.tag ("Document"),

    print kml.indent(kml_doc_setup ()),

    for icon in fac_icons:
        print kml.indent (kml_hop_style (fac_icons[icon])),

    # --- Styles for carrier hotels ---
    for ch in all_chotels:
        print  kml.indent (kml_chotel_style (ch) ),

    print kml.indent(kml_instructions ( ) ),

    # --- Render traceroutes ---
    for traceroute in traceroute_id_list:
        print kml.text (kml_traceroute (traceroute, chotel_obj, conn) ),
        
    print kml.indent (kml_chotel_layers (chotel_obj, visible_layers) ),
    print kml.end_tag ("/Document"),
    print kml.end_tag ("/kml"),








# print "Content-type: text/plain\n"

# print "hi"

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
        visible_layers = {}

    traceroute_id_list = []
    for trid in traceroute_id_strings:
        traceroute_id_list.append (int(trid))

    main(traceroute_id_list, visible_layers,
         commandline_mode=is_this_commandline)

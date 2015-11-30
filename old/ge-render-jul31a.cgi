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

MILE_TO_KM = 1.609344

# MAX_CHOTEL_DIST = EARTH_EQUAT_RADIUS * 2
MAX_CHOTEL_DIST = 3.0*MILE_TO_KM

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

def get_traceroute(conn, id):
    qres = conn.query("select * from traceroute where id=%d" % id)
    try:
        id = qres.dictresult()[0]['id']
    except IndexError:
        raise TracerouteException, "failed to find traceroute %d" % id
    return qres.dictresult()[0]


def get_tr_items(conn, id):
    qres = conn.query("select * from tr_item where traceroute_id=%d" % id)
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

def get_ip_addr_info(conn, addr):
    if addr:
        qres = conn.query("select * from ip_addr_info where ip_addr='%s'" % addr)
        d = qres.dictresult()[0]
        d['lat'] = str(d['lat'])
        d['long'] = str(d['long'])
        d['asnum'] = str(d['asnum'])
        d['country'] = str(d['mm_country'])
        d['region'] = str(d['mm_region'])
        d['city'] = str(d['mm_city'])
        d['pcode'] = str(d['mm_postal'])
        d['area_code'] = str(d['mm_area_code'])
        d['dma_code'] = str(d['mm_dma_code'])
    else:
        d={'lat': '', 'hostname': '', 'ip_addr': None, 'long': '', 'asnum': '',
           'region': '', 'city': '', 'country': '', 'pcode': '', 'area_code': '', 'dma_code': ''}
    return d

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

def get_ch_networks(conn, ch):
    if not ch.has_key('networks'):
        qres = conn.query("select name from chnetwork join ch_networks on net_id = chnetwork.id where ch_id=%d" % ch['id'])
        ch['networks'] = ','.join([d['name'] for d in qres.dictresult()])

        
class CHotels(object):
    def __init__(self, conn):
        qres = conn.query("select * from chotel")
        try:
            id = qres.dictresult()[0]['id']
        except IndexError:
            raise TracerouteException, "failed to find any carrier hotels"
        chotels = qres.dictresult()
        for ch in chotels:
            ch['xyz'] = ll_to_xyz(ch['lat'], ch['long'])
            ch['to_render'] = False
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
        
hop_style="""
  <Style id="%(id)s_nonsel">
    <IconStyle>
      <scale>0.5</scale>
      <Icon>
        <href>http://www.ixmaps.ca/ge/%(color)s8x8.png</href>
      </Icon>
    </IconStyle>
    <LabelStyle>
      <scale>1.1</scale>
    </LabelStyle>
    <BalloonStyle>
      <text><![CDATA[<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top"><td width="100%%" align="left" valign="top"> <p><a href="http://www.ixmaps.ca/"; title="IXmaps"><img src="http://www.ixmaps.ca/ge/ixmaps.png" alt="" width="270" height="60"></a></p><p>%(facility)s</p> <p><strong>$[name]</strong></p>$[description]</td></tr></table>]]></text>
    </BalloonStyle>
  </Style>
  <Style id="%(id)s_sel">
    <IconStyle>
      <scale>0.9</scale>
      <Icon>
        <href>http://www.ixmaps.ca/ge/%(color)s8x8.png</href>
      </Icon>
    </IconStyle>
    <LabelStyle>
      <scale>1.2</scale>
    </LabelStyle>
    <BalloonStyle>
      <text><![CDATA[<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top"><td width="100%%" align="left" valign="top"> <p><a href="http://www.ixmaps.ca/"; title="IXmaps"><img src="http://www.ixmaps.ca/ge/ixmaps.png" alt="" width="270" height="60"></a></p><p>%(facility)s</p> <p><strong>$[name]</strong></p>$[description]</td></tr></table>]]></text>
    </BalloonStyle>
  </Style>
  <StyleMap id="%(id)s">
    <Pair>
      <key>normal</key>
      <styleUrl>#%(id)s_nonsel</styleUrl>
    </Pair>
    <Pair>
      <key>highlight</key>
      <styleUrl>#%(id)s_sel</styleUrl>
    </Pair>
  </StyleMap>
"""

location_styles = {
    'AGF'         : { 'id': 'AGF',         'color': 'green',  'facility': 'Apple or Google facility' },
    'nearAGF'     : { 'id': 'nearAGF',     'color': 'green',  'facility': 'Near an Apple or Google facility' },
    'CAN'         : { 'id': 'CAN',         'color': 'blue',   'facility': 'In Canada' },
    'NSA'         : { 'id': 'NSA',         'color': 'red',    'facility': 'Known NSA listening post' },
    'nearNSA'     : { 'id': 'nearNSA',     'color': 'red',    'facility': 'Near a known NSA listening post' },
    'NSAposs'     : { 'id': 'NSAposs',     'color': 'red',    'facility': 'Suspected NSA listening post' },
    'nearNSAposs' : { 'id': 'nearNSAposs', 'color': 'red',    'facility': 'Near a suspected NSA listening post' },
    'CRG'         : { 'id': 'CRG',         'color': 'yellow', 'facility': 'Owned by Carlyle Real Estate - CoreSite' },
    'nearCRG'     : { 'id': 'nearCRG',     'color': 'yellow', 'facility': 'Near a facility owned by Carlyle Real Estate - CoreSite' },
    'OTH'         : { 'id': 'OTH',         'color': 'purple', 'facility': '' },  # other
}

def print_ch_style(ch):
    style = """   <Style id="ch_%(id)s_sel">
  <IconStyle>
      <scale>1.6</scale>
      <Icon>
        <href>%(image)s</href>
      </Icon>
    </IconStyle>
    <LabelStyle>
      <scale>1.2</scale>
    </LabelStyle>
    <BalloonStyle>
      <text><![CDATA[<table border="0" width="305" cellspacing="0" cellpadding="0"><tr align="left" valign="top"><td width="100%%" align="left" valign="top"> <p><a href="http://www.ixmaps.ca/"; title="IXmaps"><img src="http://www.ixmaps.ca/ge/ixmaps.png" alt="" width="270" height="60"></a></p><p>$[name]</p> <p><strong>$[name]</strong></p>$[description]</td></tr></table>]]></text>
    </BalloonStyle>
   </Style>"""

    shared = """  <StyleMap id="ch_%(id)s">
    <Pair>
      <key>normal</key>
      <styleUrl>#%(ixclass)s_nonsel</styleUrl>
    </Pair>
    <Pair>
    <key>highlight</key>
      <styleUrl>#ch_%(id)s_sel</styleUrl>
    </Pair>
  </StyleMap>"""

    print style  % ch
    print shared % ch

def print_hop_styles():
    for k in location_styles:
        print hop_style % location_styles[k]

kml_header="""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://earth.google.com/kml/2.1">
<Document>
  <Style id="docBalloonStyle">
    <BalloonStyle>
      <!-- a background color for the balloon -->
      <bgColor>40ffffbb</bgColor>
      <!-- styling of the balloon text -->
      <text><![CDATA[
      <b><font color="#CC0000" size="+3">$[name]</font></b>
      <br/><br/>
      <font face="Courier">$[description]</font>
      <br/><br/>
      ]]></text>
    </BalloonStyle>
  </Style>
  <name>Traceroute Results</name>
  <open>1</open>
  <Document>
    <name>Instructions</name>
    <Snippet maxLines="0">Instructions</Snippet>
    <description><![CDATA[
<ul><li>Click on icons to see locations of Carrier Hotels</li>
    <li>Click on location to see Carrier Hotel building</li>
    <li>Mouse over center of building to see infrastructure</li>
    </ul>"""+MAX_MIND_ATTRIBUTION+"""
  ]]></description>
    <styleUrl>#docBalloonStyle</styleUrl>
  </Document>
  <description>Select this folder and click on the &apos;Play&apos; button below, to start the tour.</description>
  <Style id="trPathStyle">
    <LineStyle>
      <color>7f0000ff</color>
      <width>4</width>
    </LineStyle>
  </Style>
  <Style id="spiderStyle">
    <LineStyle>
      <color>7fffffff</color>
      <width>2</width>
    </LineStyle>
  </Style>
"""
# (quote added to fix emacs-highlighter): "

kml_camera="""
    <Camera id="NorthAmerica">
      <longitude>-96.0</longitude>
      <latitude>45.0</latitude>
      <altitude>4500000.0</altitude>
      <heading>0.0</heading>
      <tilt>0</tilt>
      <roll>0</roll>
      <altitudeMode>absolute</altitudeMode>
    </Camera>"""


kml_trailer="""
</Document>
</kml>
"""

def get_available_hops(da):
    hop = -1
    for d in da:
        try:
            if d['hop'] > hop:
                hop = d['hop']
        except KeyError:
            pass
    return hop
	
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

def show_spider(t):
    (id, loc_to, loc_from) = t
    fmt="""   <Placemark id="spider_%d">
    <name>short walk %d</name>
     <styleUrl>#spiderStyle</styleUrl>
     <LineString>
       <tessellate>1</tessellate>
       <coordinates>%f,%f,0 %f,%f,0</coordinates>
     </LineString>
    </Placemark>"""
    print fmt % (id, id, loc_from[0], loc_from[1], loc_to[0], loc_to[1])

def show_placemark_linestring(nhops, coords):
    print """ <Placemark id="route1">
    <name>"""+str(nhops)+""" hops</name>
      <styleUrl>#trPathStyle</styleUrl>
      <LineString>
        <tessellate>1</tessellate>
          <coordinates>"""+coords+"""</coordinates>
     </LineString>
   </Placemark>"""

def show_placemark_hop(hdesc):
    if DEBUG:
        print hdesc
    else:
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

        # if (proximities.idExists(hdesc['hop'])):
        if (hdesc['ch_id']):
            urlStyle = "#ch_%(ch_id)s"
        else:
            urlStyle = "#%(ixclass)s"

        #FIXME: show pcode (if N.A.), area_code (if US), dma_code (if US)
        fmt_main = """   <Placemark id="hop_%(hop)d">
        <name>%(ixp)s</name>
        <Snippet maxLines="0"></Snippet>
        <styleUrl>""" + urlStyle + """</styleUrl>
        <Point>
          <coordinates>%(long)s,%(lat)s,0</coordinates>
        </Point>"""

        fmt_description = """        <![CDATA[name/ip/as/ms: %(host_disp)s AS%(asnum)s / %(rtts_disp)s ms<br/>
lat: %(lat)s, long: %(long)s, hop: %(hop)d<br/>
country: %(country)s<br/>
region: %(region)s<br/>
city: %(city)s<br/>]]>"""

        if (hdesc['image']):
            fmt_image = """<img src="%(image)s" />"""
        else:
            fmt_image = ""
        
        fmt_footer = """    </Placemark>"""
        print fmt_main        % hdesc
        print "        <description>" ,
        print fmt_description % hdesc
        print fmt_image       % hdesc
        print "        </description>"
        print fmt_footer      % hdesc


def show_placemark_ch(ch):
    fmt="""   <Placemark id="ch_%(id)d">
    <name>%(address)s</name>
    <Snippet maxLines="0"></Snippet>
<description><![CDATA[%(nsa_src)s<br/>
Operator: %(ch_operator)s<br/>
Building owner: %(ch_build_owner)s<br/>
Operator/Ownership source: %(ch_src)s<br/>
Networks: %(networks)s<br>
Networks source: %(isp_src)s<br/>
lat: %(lat)s, long: %(long)s<br/>
<img src="%(image)s" />
<br/>]]></description>
    <styleUrl>#ch_%(id)s</styleUrl>
    <Point>
        <coordinates>%(long)s,%(lat)s,0</coordinates>
    </Point>
    </Placemark>"""
    print fmt % ch


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

    bad_coords = [(0.0,0.0), (-95.0,60.0), (-97.0,38.0)]
    point2=(float(longitude), float(latitude))
    for c in bad_coords:
        if within(c, point2, 0.0001):
            return False
    return True

form = cgi.FieldStorage()

try:
    traceroute_id = int(form.getfirst("traceroute_id"))
except TypeError:
    traceroute_id = 0
    # traceroute_id = 54 # uncomment for use with command-line testing

if not traceroute_id:
    print "Content-Type: text/plain"
    print
    print "missing traceroute_id."
    sys.exit(0)

#print "Content-Type: application/vnd.google-earth.kml+xml"
#print "Content-Type: text/plain"
#print

conn = DBConnect.getConnection()
tr_header = get_traceroute(conn, traceroute_id)
tr_body = get_tr_items(conn, traceroute_id)
all_chotels = CHotels(conn)
proximities = Proximities()
if DEBUG:
    print tr_body
nhops = get_available_hops(tr_body)
if nhops < 1:
    print "Content-Type: text/plain"
    print
    print "no data"
else:
    if DEBUG:
        print "Content-Type: text/plain"
    else:
        print 'Content-Disposition: inline; filename="IXmaps_GE%d.kml"' % traceroute_id
        print "Content-Type: application/vnd.google-earth.kml+xml; charset=UTF-8"
    print
    print kml_header
    print_hop_styles()
    print kml_camera
    if DEBUG:
        print "nhops=", nhops
    addrs = get_available_ip_addrs(tr_body, nhops)
    if DEBUG:
        print addrs
    attempts = tr_header['attempts']
    longs = [''] * nhops
    lats = [''] * nhops
    asnums = [''] * nhops
    hostnames = [''] * nhops
    countries = [''] * nhops
    regions = [''] * nhops
    cities = [''] * nhops
    pcodes = [''] * nhops
    area_codes = [''] * nhops
    dma_codes = [''] * nhops
    chotels = [None] * nhops
    
    ixps = [''] * nhops
    ixclass = ['OTH'] * nhops
    coords = ''
    count_coords = 0
    for i in range(len(addrs)):
        addr = addrs[i]
        ai = get_ip_addr_info(conn, addr)
        if DEBUG:
            print ai
        longs[i] = longitude = ai['long']

        if longitude == 'None':
            longs[i] = longitude = ''

        lats[i] = latitude = ai['lat']
        if latitude == 'None':
            lats[i] = longitude = ''

        asnums[i] = ai['asnum']
        hostnames[i] = hostname = ai['hostname']
        countries[i] = country = ai['country']
        regions[i] = ai['region']
        cities[i] = ai['city']
        pcodes[i] = ai['pcode']
        area_codes[i] = ai['area_code']
        dma_codes[i] = ai['dma_code']
        if len(longitude) > 0 and len(latitude) > 0:
            if is_valid_coord(longitude, latitude):
                coords += longitude+','+latitude+',0 '
                count_coords += 1
                # find nearest Carrier Hotel that's within a certain distance
                chotels[i] = chotel = all_chotels.nearest(float(longitude), float(latitude), MAX_CHOTEL_DIST)

            else:
                chotel = None
            # guess whether or not we're in Canada
            if country == 'CA':
                ixclass[i] = 'CAN'
            lo = float(longitude)
            la = float(latitude)
            # guess whether we are at Folsom Street or another known NSA listening post
            if chotel:
                # The granularity of the MaxMind coordinates is 1/10000 of a degree of arc or about 11m
                # in latitude and 11m/cos(lat) in longitude.  In practice, the closest match is about
                # 50m, typically the nearest CH in urban areas is around 500m.  Therefore, always
                # put the CH and hop locations on their own places with a spider connection line.
                if chotel['nsa'] == 'Y':
                    ixclass[i] = 'nearNSA'
                elif chotel['nsa'] == 'Y?':
                    ixclass[i] = 'nearNSAposs'
                elif chotel['ch_build_owner'] == 'CoreSite':
                    ixclass[i] = 'nearCRG'
                chotel['ixclass'] = string.replace(ixclass[i], "near", "", 1)
                chotel['to_render'] = True
                get_ch_networks(conn, chotel)
                proximities.add(i, (float(longitude), float(latitude)), (chotel['long'], chotel['lat']))
            # get the name to show for the facility
            # eventually we want to say which building it is in
            if len(hostname) > 0:
                ixps[i] = hostname
            else:
                ixps[i] = addr
    if count_coords >= 2:
        if DEBUG:
            print coords
        else:
            show_placemark_linestring(nhops, coords)
    hdesc = [{}]
    for i in range(len(addrs)):
        hdesc.append({})
        if addrs[i]:
            hdesc[i]['hop'] = i
            hdesc[i]['addr'] = addrs[i]
            hdesc[i]['long'] = longs[i]
            hdesc[i]['lat'] = lats[i]
            hdesc[i]['asnum'] = asnums[i]
            hdesc[i]['hostname'] = hostnames[i]
            hdesc[i]['country'] = countries[i]
            hdesc[i]['region'] = regions[i]
            hdesc[i]['city'] = cities[i]
            hdesc[i]['pcode'] = pcodes[i]
            hdesc[i]['area_code'] = area_codes[i]
            hdesc[i]['dma_code'] = dma_codes[i]
            hdesc[i]['ixp'] = ixps[i]
            hdesc[i]['ixclass'] = ixclass[i]
            hdesc[i]['rtts'] = get_rtts(tr_body, i+1, attempts)
            
            try:
                hdesc[i]['chotel'] = chotel = all_chotels.nearest (float(hdesc[i]['long']),
                                                                   float(hdesc[i]['lat']), MAX_CHOTEL_DIST)
            except ValueError:
                pass

            if chotel:
            # if proximities.get(i):
                hdesc[i]['image'] = chotel['image']
                hdesc[i]['ch_id'] = chotel['id']
            else:
                hdesc[i]['image'] = None
                hdesc[i]['ch_id'] = None

    all_chotels.reset()
    for ch in all_chotels:
        print_ch_style (ch)

    for i in range (len(addrs)):
        show_placemark_hop(hdesc[i])

    all_chotels.reset()
    for ch in all_chotels:
        show_placemark_ch(ch)
    for px in proximities:
        show_spider(px)
            
    print kml_trailer

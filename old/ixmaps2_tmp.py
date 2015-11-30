import ixmaps

DEBUG = False

# MAX_CHOTEL_DIST = 3.0 * ixmaps.MILE_TO_KM
MAX_CHOTEL_DIST = 10.0 * ixmaps.MILE_TO_KM

class CHotels(object):
    def __init__(self, conn):
        qres = conn.query("select * from chotel")
        try:
            id = qres.dictresult()[0]['id']
        except IndexError:
            raise TracerouteException, "failed to find any carrier hotels"
        chotels = qres.dictresult()
        for ch in chotels:
            ch['xyz'] = ixmaps.ll_to_xyz(ch['lat'], ch['long'])
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

    def nearest(self, longitude, latitude, km_radius=ixmaps.EARTH_EQUAT_RADIUS*2):
        """Find the nearest carrier hotel that's within a given radius in km."""
        point = ixmaps.ll_to_xyz(latitude, longitude)
        max_dist = km_radius
        chotel = None
        for ch in self.chotels:
            dist = ixmaps.distance_km(point, ch['xyz'])
            if dist < max_dist:
                #print ch['id'], ch['long'], ch['lat'], dist, max_dist
                max_dist = dist
                chotel = ch
        return chotel

    def all_within (self, longitude, latitude, km_radius=ixmaps.EARTH_EQUAT_RADIUS*2, set_to_render=False):
        """Create a list of carrier hotels within a given radius in km."""
        point = ixmaps.ll_to_xyz(latitude, longitude)
        chotel = None
        chotel_tuple_list = []

        # --- Create list of chotels within radius ---
        for ch in self.chotels:
            dist = ixmaps.distance_km(point, ch['xyz'])
            if dist < km_radius:
                chotel_tuple_list.append ((dist, ch))

        # --- Sort chotels list ---
        chotel_tuple_list.sort()

        # --- Convert to non-tupple by removing distance meta-info ---
        chotel_list = []
        for ch in chotel_tuple_list:
            chotel_list.append (ch[1])

        # --- Set whether to render ---
        for ch in chotel_list:
            if set_to_render:
                ch['networks'] = ''
                ch['to_render'] = True

        # print chotel_list

        return chotel_list

def get_ip_addr_info(addr, conn=None):
    if conn == None:
        conn = ixmaps.DBConnect.getConnection()

    if addr:
        qres = conn.query("select * from ip_addr_info where ip_addr='%s'" % addr)

        if DEBUG:
            print "\nqres: ", qres

        if len(qres.dictresult()) > 0:

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


    if (not addr) or (len(qres.dictresult())==0):
        d={'lat': '', 'hostname': '', 'ip_addr': None, 'long': '', 'asnum': '',
           'region': '', 'city': '', 'country': '', 'pcode': '', 'area_code': '', 'dma_code': ''}
    return d


def get_ip_addr_info_list(address_list, conn=None):
    if conn == None:
        conn = ixmaps.DBConnect.getConnection()

    if address_list:

        # --- Generate SQL query ---
        addresses_str = ''
        for address in address_list:
            if address != None:
                if addresses_str != "":
                    addresses_str += ", "
                addresses_str += "'%s'" % (address)
        # print "addresses_str:", addresses_str

        if addresses_str:
            qres = conn.query("select * from ip_addr_info where ip_addr in (%s)"
                              % addresses_str)
        else:
            qres = None
            return []

        if DEBUG:
            print "\nqres: ", qres

        # if len(qres.dictresult()) > 0:

        l = len(qres.dictresult())
        ip_info_list = [None] * l
        for aa in range (0, l):

            d = qres.dictresult()[aa]
            ip_info_list[aa] = {}
            ip_info_list[aa]['lat'] = str(d['lat'])
            ip_info_list[aa]['long'] = str(d['long'])
            ip_info_list[aa]['asnum'] = str(d['asnum'])
            ip_info_list[aa]['country'] = str(d['mm_country'])
            ip_info_list[aa]['region'] = str(d['mm_region'])
            ip_info_list[aa]['city'] = str(d['mm_city'])
            ip_info_list[aa]['pcode'] = str(d['mm_postal'])
            ip_info_list[aa]['area_code'] = str(d['mm_area_code'])
            ip_info_list[aa]['dma_code'] = str(d['mm_dma_code'])
            ip_info_list[aa]['ip_addr'] = d['ip_addr']
            ip_info_list[aa]['hostname'] = d['hostname']
            ip_info_list[aa]['type'] = d['type']

    if (not address_list) or (len(qres.dictresult())==0):
        ip_info_list=[{'lat': '', 'hostname': '', 'ip_addr': None, 'long': '',
           'asnum': '', 'region': '', 'city': '', 'country': '',
           'pcode': '', 'area_code': '', 'dma_code': ''}]
    return ip_info_list

def get_country (ipInfo=None, ip=None, conn=None):

    if not ipInfo:
        ipInfo = get_ip_addr_info (ip, conn)
        
    country = ipInfo['country']

    return country

def is_chotel (ipInfo=None, ip=None, conn=None):
    
    if not ipInfo:
        ipInfo = get_ip_addr_info (ip, conn)

    # print "\nipInfo: " , ipInfo

    longitude = ipInfo['long']
    latitude = ipInfo['lat']

    if not conn:
        conn = ixmaps.DBConnect.getConnection()

    all_chotels = CHotels(conn)

    try:
        chotel = all_chotels.nearest (float(longitude), float(latitude),
                                      MAX_CHOTEL_DIST)
    except ValueError:
        return False

    if chotel and (chotel['type'] == "CH"):
        return True
    else:
        return False

def is_nsa (ipInfo=None, ip=None, conn=None):
    
    if not ipInfo:
        ipInfo = get_ip_addr_info (ip, conn)

    longitude = ipInfo['long']
    latitude = ipInfo['lat']

    if not conn:
        conn = ixmaps.DBConnect.getConnection()

    all_chotels = CHotels(conn)

    try:
        chotel_list = all_chotels.all_within (float(longitude), float(latitude),
                                      MAX_CHOTEL_DIST)
    except ValueError:
        return False

    is_there_a_chotel = False
    for chotel in chotel_list:
        if (chotel['type'] == "NSA"): #or chotel['nsa'] == "B" or chotel['nsa'] == "C" or chotel['nsa'] == "D"):
            is_there_a_chotel = True
            break

    return is_there_a_chotel

def country_flag_colour (ipInfo=None, ip=None, conn=None):
    
    country = get_country (ipInfo, ip, conn)            

    # print country

    if country == "CA":
        colour = "blue"
    elif country =="US":
        colour = "purple"
    else:
        colour = "purple"

    return colour

def chotel_flag_colour (ipInfo=None, ip=None, conn=None):
    if is_chotel (ipInfo, ip, conn):
        return "vibblue"
    else:
        return "clear"


def nsa_flag_colour (ipInfo=None, ip=None, conn=None):
    if is_nsa (ipInfo, ip, conn):
        return "nsa"
    else:
        return "clear"

def test():
    # addr = "198.32.245.112"
    addr = '66.96.31.0'
    # addr = '209.85.241.146'
    addr = "1.1.1.1"
    # addr = '128.233.192.253'
    addr = "142.150.82.0"

    ipInfo = get_ip_addr_info(addr)

    print "Country:\t\t",
    print get_country (ip=addr), ";\t",
    print country_flag_colour (ipInfo)

    print "Carrier hotel:\t\t",
    print is_chotel(ipInfo), ';\t',
    print chotel_flag_colour (ipInfo)

    print "Susp. NSA facility:\t",
    print is_nsa(ipInfo), ';\t', 
    print nsa_flag_colour (ipInfo)


if __name__ == '__main__':
    test()

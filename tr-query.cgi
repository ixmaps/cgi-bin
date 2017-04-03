#!/usr/bin/python

import sys
import pg
import time
import cgi
import cgitb; cgitb.enable()
import urllib
import ixmaps
import sys
import math
import re
import ixmaps
import ixmaps_query_types
from ixmaps import sanitize_str, xml_utils

class TracerouteException(Exception):
    pass



conn = ixmaps.DBConnect.getConnection ( )


def instances_of_strings (string):
    return string.count('%s') - string.count('%%s')

def html_generic_query_results_table(field_names, result_list, link_to,
                                      generic_headers_link_to,
                                      specific_headers_link_to):
    html = xml_utils ( )
    doc = ''

    doc += html.tag ('table id="tr-detail-table"')
    #doc += '<h1>HOla anto</h1>'
    #doc += '<table id="tr-detail-table">'
    doc += html.tag ("tr")

    for field in field_names:
        if (field in specific_headers_link_to):
            if specific_headers_link_to[field]:
                field = ("<a href='" + specific_headers_link_to[field]
                         + "'>" + field + "</a>")

        elif generic_headers_link_to:
            field = ("<a href='" + generic_headers_link_to +
                     urllib.quote_plus(str(field))
                     + "'>" + field + "</a>")

        doc += html.tagged_text ("th", field)

    doc += html.end_tag ("/tr")

    for record in result_list:
        doc += html.tag ("tr")

        if link_to:
            field0 = record[0]
            link = ("tr-query.cgi?query_type=" + link_to + "&arg="
                    + urllib.quote_plus (str(field0) ) )
            doc += html.tagged_text ("td", 'a href="' + link + '"', field0)
            # doc += html.tagged_text ("td", 'a href="' + link_to + '"', field0)
        else:
            doc += html.tagged_text ('td', record[0])

        for field in record[1:]:
            doc += html.tagged_text ("td", field)
        doc += html.end_tag ("/tr")

    doc += html.end_tag ("/table")

    return doc

def html_generic_query_results (query_info, arg=None):
    html = xml_utils ( )
    doc = ''

    if query_info.title:
        doc += html.tagged_text ('h1', query_info.title)

    if query_info.header:
        doc += html.text (query_info.header % ( (arg,) * instances_of_strings (query_info.header) ) )



    # instances_of_arg = instances_of_strings (query_info.query)
    # query = query_info.query % ((arg, ) * instances_of_arg)

    query = query_info.query % (
        (arg, ) * instances_of_strings (query_info.query) )

    q_result = conn.query (query)

    field_names = q_result.listfields ( )
    result_list = q_result.getresult ( )

    if (query_info.custom_table_function):
        doc += html.indent (
            query_info.custom_table_function (
                field_names, result_list, query_info.link_to,
                query_info.generic_headers_link_to,
                query_info.specific_headers_link_to) )

    else:
        doc += html.indent (
            html_generic_query_results_table (
                field_names, result_list, query_info.link_to,
                query_info.generic_headers_link_to,
                query_info.specific_headers_link_to) )

    doc += html.tag ('p')
    doc += html.tagged_text ('b', 'SQL Query')
    doc += html.tag ('ul')

    doc += query

    doc += html.end_tag ('/ul')
    doc += html.end_tag ('/p')

    doc += html.empty_tag ('hr')

    if query_info.footer:
        doc += html.text (query_info.footer % ( (arg,) * instances_of_strings (query_info.footer) ) )

    return doc

def main (query_type, arg):
    # "
    conn = ixmaps.DBConnect.getConnection ( )

    print "Content-Type: text/html\n"

    html = xml_utils ( )
    doc = ''

    if query_type:
        query_info = ixmaps_query_types.query_types[query_type]


        #doc += html.tag('html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en"')
        doc += '<!DOCTYPE html><html lang="en">'
        doc += html.tag("head")
        doc += html.tagged_text ("title", "IXmaps :: " + query_info.title)

        doc += '<script src="/_assets/js/jquery.min.js"></script>'
        doc += '<script src="/_assets/__build/bower_components/jquery-toastmessage-plugin/src/main/javascript/jquery.toastmessage.js"></script>'
        doc += '<script type="text/javascript" src="/_assets/js/main.js"></script>'

        doc += '<script type="text/javascript" src="/_assets/js/tr-detail.js"></script>'
        doc += '<script type="text/javascript" src="/_assets/js/gmaps.js"></script>'

        #doc += '<script type="text/javascript" src="/js/ixmaps.gm.js"></script>'
        #doc += '<link rel="stylesheet" href="/css/ix.css" type="text/css" />'
        #doc += '<link rel="stylesheet" href="/css/ix-explore.css" type="text/css" />'

        doc += html.end_tag ("/head")
        doc += html.tag ("body")
        #doc += '<h1>testing...</h1>'

        if not query_info.custom_page_function:
            doc += html.indent (html_generic_query_results (query_info, arg) )
        else:
            doc += html.indent (query_info.custom_page_function (query_info, arg) )

        doc += html.end_tag ('/body')
        doc += html.end_tag ('/html')

        print doc

        return



if __name__ == "__main__":
    # -- Get CGI variables --
    form = cgi.FieldStorage()

    query_type = form.getfirst ("query_type")
    arg = form.getfirst ("arg")

    # traceroute_id = (form.getfirst("traceroute_id") )
    # submitter = form.getfirst("submitter")
    # zip_code = form.getfirst("zip_code")
    # all_submitters = form.getfirst ("all_submitters")

    # # --- Convert traceroute from string to int ---
    # if traceroute_id != None:
        # traceroute_id = int (traceroute_id)

    # is_geek_mode_on = False if (form.getfirst ("geek") != "true" ) else True

    if not query_type:
        query_type = "all_submitters"

    # if query_type:
    main (query_type, arg)

    # else:
        # old_main (traceroute_id, submitter, zip_code, all_submitters, geek=is_geek_mode_on)

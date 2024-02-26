# encoding: utf-8

from ckanext.fuseki.backend import get_graph
import re


def common_member(a, b):
    return any(i in b for i in a)


def fuseki_show_tools(resource):
    from ckanext.fuseki.logic.action import DEFAULT_FORMATS

    format_parts = re.split("/|;", resource["format"].lower().replace(" ", ""))
    if common_member(format_parts, DEFAULT_FORMATS):
        return True
    else:
        return False


def fuseki_graph_exists(graph_id):
    return get_graph(graph_id)


def get_helpers():
    return {
        "fuseki_show_tools": fuseki_show_tools,
        "fuseki_graph_exists": fuseki_graph_exists,
    }

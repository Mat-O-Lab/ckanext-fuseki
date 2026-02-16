# encoding: utf-8

import os
import re

import requests

from ckanext.fuseki.backend import get_graph

# Retrieve the value of a configuration option
FUSEKI_URL = os.environ.get("CKANINI__CKANEXT__FUSEKI__URL", "/")
SPARKLIS_URL = os.environ.get("CKANINI__CKANEXT__FUSEKI__SPARKLIS__URL", "")


def common_member(a, b):
    return any(i in b for i in a)


def fuseki_service_available():
    url = os.environ.get("CKANINI__CKANEXT__FUSEKI__URL", "")
    if not url:
        return False  # If EXTRACT_URL is not set, return False
    try:
        # Perform a HEAD request (lightweight check) to see if the service responds
        response = requests.head(url, timeout=5, verify=False)
        if (200 <= response.status_code < 400) or response.status_code == 405:
            return True  # URL is reachable and returns a valid status code
        else:
            return False  # URL is reachable but response status is not valid
    except requests.RequestException as e:
        # If there's any issue (timeout, connection error, etc.)
        return False


def fuseki_show_tools(resource):
    from ckanext.fuseki.logic.action import DEFAULT_FORMATS

    format_parts = re.split("/|;", resource["format"].lower().replace(" ", ""))
    if common_member(format_parts, DEFAULT_FORMATS):
        return True
    else:
        return False


def fuseki_graph_exists(graph_id):
    return get_graph(graph_id)


def fuseki_query_url(pkg_dict):
    if not SPARKLIS_URL:
        # fuseki query interface
        url = "{}#/dataset/{}/query".format(FUSEKI_URL, pkg_dict["id"])
    else:
        url = "{}?title={}&endpoint={}{}".format(
            SPARKLIS_URL, pkg_dict["name"], FUSEKI_URL, pkg_dict["id"]
        )
    return url


def fuseki_sparql_url(pkg_dict):
    url = "{}{}".format(FUSEKI_URL, pkg_dict["id"])
    return url


def get_helpers():
    return {
        "fuseki_show_tools": fuseki_show_tools,
        "fuseki_graph_exists": fuseki_graph_exists,
        "fuseki_query_url": fuseki_query_url,
        "fuseki_sparql_url": fuseki_sparql_url,
    }

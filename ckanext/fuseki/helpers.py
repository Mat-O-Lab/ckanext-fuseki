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
    from ckan.plugins import toolkit
    
    if not SPARKLIS_URL:
        # Use CKAN proxy URL for Fuseki query interface
        # Pattern: /dataset/{id}/fuseki/$/query
        url = toolkit.url_for('fuseki.fuseki_proxy', 
                              id=pkg_dict['id'], 
                              service_path='query',
                              qualified=True)
    else:
        # Sparklis interface - use CKAN proxy SPARQL endpoint
        sparql_endpoint = toolkit.url_for('fuseki.fuseki_proxy', 
                                         id=pkg_dict['id'], 
                                         service_path='sparql',
                                         qualified=True)
        url = "{}?title={}&endpoint={}&entity_lexicon_select=http%3A//www.w3.org/2000/01/rdf-schema%23label&concept_lexicons_select=http%3A//www.w3.org/2000/01/rdf-schema%23label".format(
            SPARKLIS_URL, pkg_dict["name"], sparql_endpoint
        )
    return url


def fuseki_sparql_url(pkg_dict):
    """
    Returns the SPARQL endpoint URL for a dataset.
    
    Uses the CKAN proxy endpoint instead of direct Fuseki access
    for security (CKAN authentication required).
    
    Returns: /dataset/{id}/fuseki/$/sparql
    """
    from ckan.plugins import toolkit
    
    # Return CKAN proxy URL - this handles authentication
    # Pattern: /dataset/{id}/fuseki/$/{service_path}
    url = toolkit.url_for('fuseki.fuseki_proxy', 
                          id=pkg_dict['id'], 
                          service_path='sparql',
                          qualified=True)
    return url




def get_helpers():
    return {
        "fuseki_show_tools": fuseki_show_tools,
        "fuseki_graph_exists": fuseki_graph_exists,
        "fuseki_query_url": fuseki_query_url,
        "fuseki_sparql_url": fuseki_sparql_url,
    }

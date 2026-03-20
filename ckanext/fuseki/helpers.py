# encoding: utf-8

import re

import requests
from ckan.common import config

from ckanext.fuseki.backend import get_graph


def common_member(a, b):
    return any(i in b for i in a)


def fuseki_service_available():
    # Prefer internal_url (direct container address) over the public-facing url
    # to avoid routing through nginx from inside CKAN.
    base = config.get("ckanext.fuseki.internal_url", "") or config.get("ckanext.fuseki.url", "")
    if not base:
        return False
    ssl_verify = config.get("ckanext.fuseki.ssl_verify", True)
    # /$/ping is explicitly anon in shiro.ini and is the canonical health endpoint
    ping_url = base.rstrip("/") + "/$/ping"
    try:
        response = requests.get(ping_url, timeout=5, verify=ssl_verify)
        return response.status_code == 200
    except requests.RequestException:
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

    sparklis_url = config.get("ckanext.fuseki.sparklis_url", "")
    if not sparklis_url:
        # Use the built-in YASGUI query page
        url = toolkit.url_for('fuseki.query', id=pkg_dict['id'], qualified=True)
    else:
        # Sparklis interface - use CKAN proxy SPARQL endpoint
        sparql_endpoint = toolkit.url_for('fuseki.fuseki_proxy',
                                         id=pkg_dict['id'],
                                         service_path='sparql',
                                         qualified=True)
        url = "{}?title={}&endpoint={}&entity_lexicon_select=http%3A//www.w3.org/2000/01/rdf-schema%23label&concept_lexicons_select=http%3A//www.w3.org/2000/01/rdf-schema%23label".format(
            sparklis_url, pkg_dict["name"], sparql_endpoint
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

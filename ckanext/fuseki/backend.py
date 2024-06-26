# -*- coding: utf-8 -*-

import os, logging
from ckan.common import config
import requests
from rdflib import Graph
from ckan.plugins.toolkit import asbool


# from io import BytesIO

log = logging.getLogger(__name__)
CHUNK_SIZE = 16 * 1024  # 16kb
SSL_VERIFY = asbool(os.environ.get("FUSEKI_SSL_VERIFY", True))
if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()


def graph_delete(graph_id: str):
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    result = dict(resource_id=graph_id)
    try:
        jena_dataset_delete_url = jena_base_url + "$/datasets/{graph_id}".format(
            graph_id=graph_id
        )
        jena_dataset_delete_res = requests.delete(
            jena_dataset_delete_url,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        jena_dataset_delete_res.raise_for_status()
    except Exception as e:
        pass

    return result


def resource_upload(resource, graph_url, api_key=""):
    graph_url += "/data"
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    headers = {}
    if api_key:
        if ":" in api_key:
            header, key = api_key.split(":")
        else:
            header, key = "Authorization", api_key
        headers[header] = key
    response = requests.get(resource["url"], headers=headers, verify=SSL_VERIFY)
    response.raise_for_status()
    # file_object = BytesIO(response.content)
    file_type = resource["mimetype"]
    # parse and reserialize json-ld data because fuseki seams unable to read compacted json-ld
    if "ld+json" in file_type:
        file_data = (
            Graph()
            .parse(data=response.text, format="json-ld")
            .serialize(format="json-ld")
        )
    else:
        file_data = response.text
    # file_type=resource['format']
    log.debug(file_type)
    # file_data = response.text
    log.debug(response.headers)
    files = {"file": (resource["name"], file_data, file_type, {"Expires": "0"})}
    # files = {"file": (resource["name"], file_object)}
    jena_upload_res = requests.post(
        graph_url, files=files, auth=(jena_username, jena_password), verify=SSL_VERIFY
    )
    jena_upload_res.raise_for_status()
    return True


def resource_exists(id):
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    res_exists = False
    try:
        jena_dataset_stats_url = jena_base_url + "$/stats/{resource_id}".format(
            resource_id=id
        )
        jena_dataset_stats_res = requests.get(
            jena_dataset_stats_url,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            res_exists = True
    except Exception as e:
        pass
    return res_exists


def get_graph(graph_id):
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")

    try:
        jena_dataset_stats_url = jena_base_url + "$/stats/{graph_id}".format(
            graph_id=graph_id
        )
        jena_dataset_stats_res = requests.get(
            jena_dataset_stats_url,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            result = jena_base_url + "{graph_id}".format(graph_id=graph_id)
    except Exception as e:
        result = False
    return result


def graph_create(graph_id: str):
    fields = [dict(type="text", id="rdf")]
    # model = _get_or_bust(context, 'model')
    # resource = model.Resource.get(data_dict['resource_id'])
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")

    jena_dataset_create_url = jena_base_url + "$/datasets"
    jena_dataset_create_res = requests.post(
        jena_dataset_create_url,
        params={"dbName": graph_id, "dbType": "mem"},
        auth=(jena_username, jena_password),
        verify=SSL_VERIFY,
    )
    jena_dataset_create_res.raise_for_status()
    return jena_base_url + "{graph_id}".format(graph_id=graph_id)

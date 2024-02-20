# -*- coding: utf-8 -*-

import logging
from ckan.common import config
import ckan.plugins.toolkit as toolkit
import ckan.logic as logic
import requests
import json

log = logging.getLogger(__name__)
_get_or_bust = logic.get_or_bust

CHUNK_SIZE = 16 * 1024  # 16kb


def search_sparql(context, data_dict):
    resource_id = data_dict["resource_id"]
    q = data_dict.get("q", "")
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    rdf_data = ""
    try:
        jena_dataset_query_url = jena_base_url + "{resource_id}/query".format(
            resource_id=resource_id
        )
        jena_dataset_query_res = requests.post(
            jena_dataset_query_url,
            params={"query": q},
            auth=(jena_username, jena_password),
        )
        jena_dataset_query_res.raise_for_status()
        if jena_dataset_query_res.status_code == requests.codes.ok:
            res = ""
            for chunk in jena_dataset_query_res.iter_content(CHUNK_SIZE):
                res += chunk
            rdf_data = json.loads(res)
    except Exception as e:
        pass
    result = dict(
        resource_id=resource_id,
        fields=[dict(type="text", id="rdf")],
        records=rdf_data,
        query=q,
    )
    return result


def delete(context, data_dict):
    resource_id = data_dict["resource_id"]
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    result = dict(resource_id=data_dict["resource_id"])
    try:
        jena_dataset_delete_url = jena_base_url + "$/datasets/{resource_id}".format(
            resource_id=resource_id
        )
        jena_dataset_delete_res = requests.delete(
            jena_dataset_delete_url, auth=(jena_username, jena_password)
        )
        jena_dataset_delete_res.raise_for_status()
    except Exception as e:
        pass

    return result


def create(context, data_dict):
    fields = [dict(type="text", id="rdf")]
    # model = _get_or_bust(context, 'model')
    # resource = model.Resource.get(data_dict['resource_id'])
    resource = data_dict["resource"]
    resource_id = data_dict["resource_id"]
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")

    jena_dataset_create_url = jena_base_url + "$/datasets"
    jena_dataset_create_res = requests.post(
        jena_dataset_create_url,
        params={"dbName": resource_id, "dbType": "mem"},
        auth=(jena_username, jena_password),
    )
    jena_dataset_create_res.raise_for_status()
    jena_upload_url = jena_base_url
    jena_upload_url += "{resource_id}/data".format(resource_id=resource_id)
    file_name = resource["name"]
    file_type = resource["mimetype"]
    response = requests.get(resource["url"])
    file_data = response.text
    log.debug(file_data[:200])
    files = {"file": (file_name, file_data, file_type, {"Expires": "0"})}
    jena_upload_res = requests.post(
        jena_upload_url, files=files, auth=(jena_username, jena_password)
    )
    jena_upload_res.raise_for_status()

    return dict(resource_id=data_dict["resource_id"], fields=fields)


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
            jena_dataset_stats_url, auth=(jena_username, jena_password)
        )
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            res_exists = True
    except Exception as e:
        pass
    return res_exists

def get_graph(id):
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    result = False
    try:
        jena_dataset_stats_url = jena_base_url + "$/stats/{resource_id}".format(
            resource_id=id
        )
        jena_dataset_stats_res = requests.get(
            jena_dataset_stats_url, auth=(jena_username, jena_password)
        )
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            result = jena_base_url + "{resource_id}".format(resource_id=id)
    except Exception as e:
        pass
    return result

def graph_create(resource):
    fields = [dict(type="text", id="rdf")]
    # model = _get_or_bust(context, 'model')
    # resource = model.Resource.get(data_dict['resource_id'])
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")

    jena_dataset_create_url = jena_base_url + "$/datasets"
    jena_dataset_create_res = requests.post(
        jena_dataset_create_url,
        params={"dbName": resource['id'], "dbType": "mem"},
        auth=(jena_username, jena_password),
    )
    jena_dataset_create_res.raise_for_status()
    jena_upload_url = jena_base_url
    jena_upload_url += "{resource_id}/data".format(resource_id=resource['id'])
    file_name = resource["name"]
    file_type = resource["mimetype"]
    response = requests.get(resource["url"])
    file_data = response.text
    log.debug(file_data[:200])
    files = {"file": (file_name, file_data, file_type, {"Expires": "0"})}
    jena_upload_res = requests.post(
        jena_upload_url, files=files, auth=(jena_username, jena_password)
    )
    jena_upload_res.raise_for_status()

    return jena_base_url + "{resource_id}/data".format(resource_id=resource['id'])


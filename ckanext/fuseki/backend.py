# -*- coding: utf-8 -*-

import logging
from ckan.common import config
import ckan.plugins.toolkit as toolkit
import ckan.logic as logic
import os
import pprint
import requests
import json
import hashlib
import tempfile

log = logging.getLogger(__name__)
_get_or_bust = logic.get_or_bust

CHUNK_SIZE = 16 * 1024 # 16kb

def search_sparql(context, data_dict):
    resource_id = data_dict['resource_id']
    q = data_dict.get('q', '')
    jena_base_url = config.get('ckan.jena.fuseki.url')
    jena_username = config.get('ckan.jena.fuseki.username')
    jena_password = config.get('ckan.jena.fuseki.password')
    rdf_data = ''
    try:
        jena_dataset_query_url = jena_base_url + '{resource_id}/query'.format(resource_id=resource_id)
        jena_dataset_query_res = requests.post(
            jena_dataset_query_url,
            params={'query': q},
            auth=(jena_username, jena_password)
        )
        jena_dataset_query_res.raise_for_status()
        if jena_dataset_query_res.status_code == requests.codes.ok:
            res = ''
            for chunk in jena_dataset_query_res.iter_content(CHUNK_SIZE):
                res += chunk
            rdf_data = json.loads(res)
    except Exception, e:
        pass
    result = dict(resource_id=resource_id, fields=[dict(type='text', id='rdf')],
                    records=rdf_data, query=q)
    return result

def delete(context, data_dict):
    resource_id = data_dict['resource_id']
    jena_base_url = config.get('ckan.jena.fuseki.url')
    jena_username = config.get('ckan.jena.fuseki.username')
    jena_password = config.get('ckan.jena.fuseki.password')
    result = dict(resource_id=data_dict['resource_id'])
    try:
        jena_dataset_delete_url = jena_base_url + '$/datasets/{resource_id}'.format(resource_id=resource_id)
        jena_dataset_delete_res = requests.delete(jena_dataset_delete_url, auth=(jena_username, jena_password))
        jena_dataset_delete_res.raise_for_status()
    except Exception, e:
        pass

    return result

def create(context, data_dict):
    fields = [dict(type='text', id='rdf')]
    model = _get_or_bust(context, 'model')
    resource = model.Resource.get(data_dict['resource_id'])
    resource_id = data_dict['resource_id']
    jena_base_url = config.get('ckan.jena.fuseki.url')
    jena_username = config.get('ckan.jena.fuseki.username')
    jena_password = config.get('ckan.jena.fuseki.password')
    try:
        jena_dataset_create_url = jena_base_url + '$/datasets'
        jena_dataset_create_res= requests.post(
            jena_dataset_create_url,
            params={'dbName': resource_id,
                    'dbType': 'mem'},
            auth=(jena_username, jena_password)
        )
        jena_dataset_create_res.raise_for_status()
        jena_upload_url = jena_base_url
        jena_upload_url += '{resource_id}/data'.format(resource_id=resource_id)
        file_name = resource.name
        file_type = resource.mimetype
        file_data = ''
        for i in data_dict['records']:
            file_data += i
        files = {'file': (file_name, file_data, file_type, {'Expires': '0'})}
        jena_upload_res = requests.post(
            jena_upload_url,
            files=files,
            auth=(jena_username, jena_password)
        )
        jena_upload_res.raise_for_status()
    except Exception, e:
        raise Exception({
            'jena dataset create error': e
        })
    return dict(resource_id=data_dict['resource_id'], fields=fields)

def resource_exists(id):
    jena_base_url = config.get('ckan.jena.fuseki.url')
    jena_username = config.get('ckan.jena.fuseki.username')
    jena_password = config.get('ckan.jena.fuseki.password')
    res_exists = False
    try:
        jena_dataset_stats_url = jena_base_url + '$/stats/{resource_id}'.format(resource_id=id)
        jena_dataset_stats_res = requests.get(jena_dataset_stats_url, auth=(jena_username, jena_password))
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            res_exists = True
    except Exception, e:
        pass
    return res_exists

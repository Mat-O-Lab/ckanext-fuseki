# encoding: utf-8

import logging
import json
import os

import ckan.lib.search as search
import ckan.lib.navl.dictization_functions
import ckan.logic as logic
import ckan.plugins as p
from ckan.common import config
import ckanext.fuseki.backend as backend

log = logging.getLogger(__name__)
_get_or_bust = logic.get_or_bust

DEFAULT_FORMATS = [
    'ttl', 'nt', 'nq', 'trig', 'rdf', 'owl', 'jsonld', 'trdf', 'rt', 'rj', 'trix', 'n3'
]

def jena_create(context, data_dict):
    model = _get_or_bust(context, 'model')
    resource_format = data_dict.get('format', None)
    if resource_format.lower() in DEFAULT_FORMATS:
        records = data_dict.pop('records', None)
        resource = data_dict.pop('resource', None)
        resource_dict = None
        if records:
            data_dict['records'] = records
        if resource:
            data_dict['resource'] = resource
        p.toolkit.check_access('jena_create', context, data_dict)
        if 'resource' in data_dict and 'resource_id' in data_dict:
            raise p.toolkit.ValidationError({
                'resource': ['resource cannot be used with resource_id']
            })
        if 'resource' not in data_dict and 'resource_id' not in data_dict:
            raise p.toolkit.ValidationError({
                'resource_id': ['resource_id or resource required']
            })
        res_exists = backend.resource_exists(data_dict['resource_id'])
        if res_exists:
            backend.delete(context, data_dict)
        result = backend.create(context, data_dict)
        set_jena_active_flag(model, data_dict, True)
        return result

def jena_delete(context, data_dict):
    p.toolkit.check_access('jena_delete', context, data_dict)
    if not data_dict.pop('force', False):
        resource_id = data_dict['resource_id']
        _check_read_only(context, resource_id)
    res_id = data_dict['resource_id']
    res_exists = backend.resource_exists(res_id)
    model = _get_or_bust(context, 'model')
    resource = model.Resource.get(data_dict['resource_id'])
    if res_exists:
        result = backend.delete(context, data_dict)
    else:
        if resource.extras.get('jena_active') is True:
            log.debug(
                'jena_active is True but there is no resource {0} in jena'.format(resource.id)
            )

    if (not data_dict.get('filters') and
            resource.extras.get('jena_active') is True):
        log.debug(
            'Setting jena_active=False on resource {0}'.format(
                resource.id)
        )
        set_jena_active_flag(model, data_dict, False)

    result.pop('id', None)
    result.pop('connection_url', None)
    return result

@logic.side_effect_free
def jena_search_sparql(context, data_dict):
    if 'resource_id' not in data_dict:
        raise p.toolkit.ObjectNotFound(p.toolkit._('Resource was not found.'))
    res_id = data_dict['resource_id']
    res_exists = backend.resource_exists(res_id)
    if res_exists:
        p.toolkit.check_access('jena_search_sparql', context, data_dict)            
        result = backend.search_sparql(context, data_dict)
        return result
    if not res_exists:
        raise p.toolkit.ObjectNotFound(p.toolkit._(
            'Resource "{0}" was not found.'.format(res_id)
        ))

def set_jena_active_flag(model, data_dict, flag):
    update_dict = {'jena_active': flag}
    res_query = model.Session.query(
        model.resource_table.c.extras,
        model.resource_table.c.package_id
    ).filter(
        model.Resource.id == data_dict['resource_id']
    )
    extras, package_id = res_query.one()
    extras.update(update_dict)
    res_query.update({'extras': extras}, synchronize_session=False)
    model.Session.query(model.resource_revision_table).filter(
        model.ResourceRevision.id == data_dict['resource_id'],
        model.ResourceRevision.current is True
    ).update({'extras': extras}, synchronize_session=False)

    model.Session.commit()
    psi = search.PackageSearchIndex()
    solr_query = search.PackageSearchQuery()
    q = {
        'q': 'id:"{0}"'.format(package_id),
        'fl': 'data_dict',
        'wt': 'json',
        'fq': 'site_id:"%s"' % config.get('ckan.site_id'),
        'rows': 1
    }
    for record in solr_query.run(q)['results']:
        solr_data_dict = json.loads(record['data_dict'])
        for resource in solr_data_dict['resources']:
            if resource['id'] == data_dict['resource_id']:
                resource.update(update_dict)
                psi.index_package(solr_data_dict)
                break

def _resource_exists(context, data_dict):
    model = _get_or_bust(context, 'model')
    res_id = _get_or_bust(data_dict, 'resource_id')
    if not model.Resource.get(res_id):
        return False
    return backend.resource_exists(res_id)

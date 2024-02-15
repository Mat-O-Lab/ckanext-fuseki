# encoding: utf-8

import logging
import os

import ckan.plugins as p
import ckan.logic as logic
import ckan.model as model
from ckan.plugins.toolkit import get_action
from ckan.model.core import State
from ckan.common import config, request
from ckan.lib import uploader

import paste.fileapp
import ckanext.jena.logic.action as action
import ckanext.jena.logic.auth as auth
import ckanext.jena.backend as backend

log = logging.getLogger(__name__)

class JenaPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)
    p.implements(p.IResourceController, inherit=True)
    
    # IConfigurer

    def update_config(self, config):
        return None

    def configure(self, config):
        required_keys = ('ckan.jena.fuseki')
        for key in required_keys:
            if config.get(key) is None:
                raise RuntimeError('Required configuration option {0} not found.'.format(key))
        self.config = config

    # IActions

    def get_actions(self):
        actions = {
            'jena_create': action.jena_create,
            'jena_delete': action.jena_delete,
            'jena_search_sparql': action.jena_search_sparql
        }
        return actions

    # IAuthFunctions

    def get_auth_functions(self):
        return {
            'jena_create': auth.jena_create,
            'jena_delete': auth.jena_delete,
            'jena_search_sparql': auth.jena_search_sparql,
        }
    
    # IResourceController

    def after_create(self, context, resource):
        if resource.get('url_type') == 'upload':
            upload = uploader.get_resource_uploader(resource)
            filepath = upload.get_path(resource['id'])
            file = open(filepath, mode='r')
            content = file.read()
            file.close()
            resource['resource_id'] = resource['id']
            resource['records'] = content
            return get_action(u'jena_create')(context, resource)
        return resource

    def after_update(self, context, resource):
        if resource.get('url_type') == 'upload':
            upload = uploader.get_resource_uploader(resource)
            filepath = upload.get_path(resource['id'])
            file = open(filepath, mode='r')
            content = file.read()
            file.close()
            resource['resource_id'] = resource['id']
            resource['records'] = content
            return get_action(u'jena_create')(context, resource)
        return get_action(u'jena_create')(context, resource)

    def after_delete(self, context, resources):
        model = context['model']
        pkg = context['package']
        res_query = model.Session.query(model.Resource)
        query = res_query.filter(
            model.Resource.package_id == pkg.id,
            model.Resource.state == State.DELETED
        )
        deleted = [
            res for res in query.all()
            if res.extras.get('jena_active') is True]
        for res in deleted:
            res_exists = backend.resource_exists(res.id)
            if res_exists:
                backend.delete(context, {'resource_id': res.id})
            res.extras['jena_active'] = False
            res_query.update(
                {'extras': res.extras}, synchronize_session=False)

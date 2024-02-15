# encoding: utf-8

import ckan.plugins as p

def jena_auth(context, data_dict, privilege='resource_update'):
    if 'id' not in data_dict:
        data_dict['id'] = data_dict.get('resource_id')
    user = context.get('user')
    authorized = p.toolkit.check_access(privilege, context, data_dict)
    if not authorized:
        return {
            'success': False,
            'msg': p.toolkit._(
                'User {0} not authorized to update resource {1}'
                    .format(str(user), data_dict['id'])
            )
        }
    else:
        return {'success': True}


def jena_create(context, data_dict):
    if 'resource' in data_dict and data_dict['resource'].get('package_id'):
        data_dict['id'] = data_dict['resource'].get('package_id')
        privilege = 'package_update'
    else:
        privilege = 'resource_update'
    return jena_auth(context, data_dict, privilege=privilege)

def jena_delete(context, data_dict):
    return jena_auth(context, data_dict)

@p.toolkit.auth_allow_anonymous_access
def jena_search_sparql(context, data_dict):
    return jena_auth(context, data_dict, 'resource_show')

from flask import Blueprint
from flask.views import MethodView
import ckan.plugins.toolkit as toolkit
import ckan.lib.helpers as core_helpers
import ckan.lib.base as base

from flask import request

log = __import__("logging").getLogger(__name__)


blueprint = Blueprint("fuseki", __name__)

class FusekiView(MethodView):
    def post(self, id: str, resource_id: str):
        if 'create/update' in request.form:
            toolkit.get_action('fuseki_update')(
                    {}, {
                        'resource_id': resource_id
                    }
                )
            
            # try:
            #     toolkit.get_action('jena_create')(
            #         {}, {
            #             'resource_id': resource_id
            #         }
            #     )
            # except toolkit.ValidationError:
            #     log.debug(toolkit.ValidationError)
        elif 'delete' in request.form:
            toolkit.get_action('fuseki_delete')(
                    {}, {
                        'resource_id': resource_id
                    }
                )

        return core_helpers.redirect_to(
            'fuseki.fuseki', id=id, resource_id=resource_id
        )
       

    def get(self, id: str, resource_id: str):
        try:
            pkg_dict = toolkit.get_action('package_show')({}, {'id': id})
            resource = toolkit.get_action('resource_show'
                                          )({}, {
                                              'id': resource_id
                                          })

            # backward compatibility with old templates
            toolkit.g.pkg_dict = pkg_dict
            toolkit.g.resource = resource

        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            base.abort(404, 'Resource not found')
        status=toolkit.get_action('fuseki_update_status')(
            {}, {
                        'resource_id': resource_id
                    }
        )
    
        return base.render(
            'fuseki/status.html',
            extra_vars={
                'pkg_dict': pkg_dict,
                'resource': resource,
                'status': status,
            }
        )

        
blueprint.add_url_rule(
    '/dataset/<id>/resource/<resource_id>/fuseki',
    view_func=FusekiView.as_view(str('fuseki'))
)

def get_blueprint():
    return blueprint
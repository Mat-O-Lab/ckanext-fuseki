# encoding: utf-8

import logging
import os
from typing import Any

import ckan.model as model
import ckan.plugins as p
from ckan.common import CKANConfig
from ckan.config.declaration import Declaration, Key

import ckanext.fuseki.logic.action as action
import ckanext.fuseki.logic.auth as auth
from ckanext.fuseki import helpers, views

log = logging.getLogger(__name__)


class JenaPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.IConfigDeclaration)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)
    p.implements(p.IResourceController, inherit=True)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IBlueprint)

    # IConfigurer

    def update_config(self, config: CKANConfig):
        p.toolkit.add_template_directory(config, "templates")
        p.toolkit.add_resource("assets", "fuseki")

    # IConfigDeclaration

    def declare_config_options(self, declaration: Declaration, key: Key):
        declaration.annotate("Fuseki")
        group = key.ckanext.fuseki
        declaration.declare(group.url, "/fuseki")
        declaration.declare(group.username, "admin")
        declaration.declare(group.password, "admin")
        declaration.declare(
            group.formats,
            "turtle text/turtle n3 nt hext trig longturtle xml json-ld ld+json jsonld",
        )

    # IActions

    def get_actions(self):
        actions = action.get_actions()
        return actions

    # IAuthFunctions

    def get_auth_functions(self):
        return auth.get_auth_functions()

    # IResourceController

    # def after_create(self, context, resource):
    #     if resource.get("url_type") == "upload":
    #         upload = uploader.get_resource_uploader(resource)
    #         filepath = upload.get_path(resource["id"])
    #         file = open(filepath, mode="r")
    #         content = file.read()
    #         file.close()
    #         resource["resource_id"] = resource["id"]
    #         resource["records"] = content
    #         return get_action("jena_create")(context, resource)
    #     return resource

    # def after_update(self, context, resource):
    #     if resource.get("url_type") == "upload":
    #         upload = uploader.get_resource_uploader(resource)
    #         filepath = upload.get_path(resource["id"])
    #         file = open(filepath, mode="r")
    #         content = file.read()
    #         file.close()
    #         logging.info("fuseki ext got update resource event")
    #         resource["resource_id"] = resource["id"]
    #         resource["records"] = content
    #         return get_action("jena_create")(context, resource)
    #     return get_action("jena_create")(context, resource)

    # def after_delete(self, context, resources):
    #     model = context["model"]
    #     pkg = context["package"]
    #     res_query = model.Session.query(model.Resource)
    #     query = res_query.filter(
    #         model.Resource.package_id == pkg.id, model.Resource.state == State.DELETED
    #     )
    #     deleted = [res for res in query.all() if res.extras.get("jena_active") is True]
    #     for res in deleted:
    #         res_exists = backend.resource_exists(res.id)
    #         if res_exists:
    #             backend.delete(context, {"resource_id": res.id})
    #         res.extras["jena_active"] = False
    #         res_query.update({"extras": res.extras}, synchronize_session=False)

    def _update_graph(self, resource_dict: dict[str, Any]):
        context = {"model": model, "ignore_auth": True, "defer_commit": True}
        format = resource_dict.get("format", None)
        submit = format and format.lower() in action.DEFAULT_FORMATS
        if not submit:
            return

        try:
            log.debug(
                "Submitting resource {0} with format {1}".format(
                    resource_dict["id"], format
                )
                + " to fuseki_update"
            )
            p.toolkit.get_action("fuseki_update")(context, {"id": resource_dict["id"]})

        except p.toolkit.ValidationError as e:
            log.critical(e)
            pass

    # ITemplateHelpers

    def get_helpers(self):
        return helpers.get_helpers()

    # IBlueprint

    def get_blueprint(self):
        return views.get_blueprint()

import ckan.lib.base as base
import ckan.lib.helpers as core_helpers
import ckan.plugins.toolkit as toolkit
from ckan.common import _
from flask import Blueprint, redirect, request
from flask.views import MethodView

from ckanext.fuseki.backend import Reasoners
from ckanext.fuseki.helpers import fuseki_query_url, fuseki_service_available

log = __import__("logging").getLogger(__name__)


blueprint = Blueprint("fuseki", __name__)


class FusekiView(MethodView):
    def post(self, id: str):
        try:
            pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
            if "create/update" in request.form:
                to_upload = request.form.getlist("resid")
                persistent = bool(request.form.get("persistent"))
                reasoning = bool(request.form.get("reasoning"))
                reasoner = request.form.get("reasoner")

                log.debug(
                    "reasoning enabled: {}; persistent dataset: {}; reasoner: {}".format(
                        reasoning, persistent, reasoner
                    )
                )
                log.debug("ressource ids to upload: {}".format(to_upload))
                if to_upload:
                    toolkit.get_action("fuseki_update")(
                        {},
                        {
                            "pkg_id": pkg_dict["id"],
                            "resource_ids": request.form.getlist("resid"),
                            "persistent": persistent,
                            "reasoning": reasoning,
                            "reasoner": reasoner,
                        },
                    )
            elif "delete" in request.form:
                toolkit.get_action("fuseki_delete")(
                    {},
                    {
                        "id": pkg_dict["id"],
                    },
                )
        except toolkit.ObjectNotFound:
            base.abort(404, "Dataset not found")
        except toolkit.NotAuthorized:
            base.abort(403, _("Not authorized to see this page"))

        log.debug(toolkit.redirect_to("fuseki.fuseki", id=id))
        return toolkit.redirect_to("fuseki.fuseki", id=id)
        # return core_helpers.redirect_to("fuseki.fuseki", id=id)

    def get(self, id: str):
        pkg_dict = {}
        try:
            pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
            status = toolkit.get_action("fuseki_update_status")(
                {}, {"pkg_id": pkg_dict["id"]}
            )
        except toolkit.ObjectNotFound:
            base.abort(404, "Dataset not found")
        except toolkit.NotAuthorized:
            base.abort(403, _("Not authorized to see this page"))

        return base.render(
            "fuseki/status.html",
            extra_vars={
                "pkg_dict": pkg_dict,
                "resources": pkg_dict["resources"],
                "status": status,
                "service_status": fuseki_service_available(),
                "reasoners": Reasoners.choices(),
            },
        )


class StatusView(MethodView):

    def get(self, id: str):
        pkg_dict = {}
        try:
            pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
            status = toolkit.get_action("fuseki_update_status")(
                {}, {"pkg_id": pkg_dict["id"]}
            )
        except toolkit.ObjectNotFound:
            base.abort(404, "Dataset not found")
        except toolkit.NotAuthorized:
            base.abort(403, _("Not authorized to see this page"))

        if "logs" in status.keys():
            for index, item in enumerate(status["logs"]):
                status["logs"][index]["timestamp"] = (
                    core_helpers.time_ago_from_timestamp(item["timestamp"])
                )
                if item["level"] == "DEBUG":
                    status["logs"][index]["alertlevel"] = "info"
                    status["logs"][index]["icon"] = "bug-slash"
                    status["logs"][index]["class"] = "success"
                elif item["level"] == "INFO":
                    status["logs"][index]["alertlevel"] = "info"
                    status["logs"][index]["icon"] = "check"
                    status["logs"][index]["class"] = "success"
                else:
                    status["logs"][index]["alertlevel"] = "error"
                    status["logs"][index]["icon"] = "exclamation"
                    status["logs"][index]["class"] = "failure"
        if "graph" in status.keys():
            status["queryurl"] = fuseki_query_url(pkg_dict)
        return {"pkg_dict": pkg_dict, "status": status}


def query_view(id: str):
    pkg_dict = {}
    try:
        pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
    except toolkit.ObjectNotFound:
        base.abort(404, "Dataset not found")
    except toolkit.NotAuthorized:
        base.abort(403, _("Not authorized to see this page"))

    return redirect(fuseki_query_url(pkg_dict), code=302)


blueprint.add_url_rule(
    "/dataset/<id>/fuseki", view_func=FusekiView.as_view(str("fuseki"))
)
blueprint.add_url_rule(
    "/dataset/<id>/fuseki/status",
    view_func=StatusView.as_view(str("status")),
)

blueprint.add_url_rule(
    "/dataset/<id>/fuseki/query",
    view_func=query_view,
    endpoint="query",
    methods=["GET"],
)


def get_blueprint():
    return blueprint

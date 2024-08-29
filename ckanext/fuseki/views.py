from flask import Blueprint
from flask.views import MethodView
import ckan.plugins.toolkit as toolkit
import ckan.lib.helpers as core_helpers
import ckan.lib.base as base
from flask import request
from ckanext.fuseki.helpers import fuseki_query_url
from ckanext.fuseki.backend import Reasoners

log = __import__("logging").getLogger(__name__)


blueprint = Blueprint("fuseki", __name__)


class FusekiView(MethodView):
    def post(self, id: str):
        try:
            pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            base.abort(404, "Resource not found")
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
                    "pkg_id": pkg_dict["id"],
                },
            )
        log.debug(toolkit.redirect_to("fuseki.fuseki", id=id))
        return toolkit.redirect_to("fuseki.fuseki", id=id)
        # return core_helpers.redirect_to("fuseki.fuseki", id=id)

    def get(self, id: str):
        pkg_dict = {}
        try:
            pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            base.abort(404, "Resource not found")
        status = toolkit.get_action("fuseki_update_status")(
            {}, {"pkg_id": pkg_dict["id"]}
        )
        return base.render(
            "fuseki/status.html",
            extra_vars={
                "pkg_dict": pkg_dict,
                "resources": pkg_dict["resources"],
                "status": status,
                "reasoners": Reasoners.choices(),
            },
        )


class StatusView(MethodView):

    def get(self, id: str):
        pkg_dict = {}
        try:
            pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            base.abort(404, "Resource not found")

        status = toolkit.get_action("fuseki_update_status")(
            {}, {"pkg_id": pkg_dict["id"]}
        )
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
        # return base.render(
        #     "fuseki/logs.html",
        #     extra_vars={"pkg_dict": pkg_dict, "status": status},
        # )


blueprint.add_url_rule(
    "/dataset/<id>/fuseki", view_func=FusekiView.as_view(str("fuseki"))
)
blueprint.add_url_rule(
    "/dataset/<id>/fuseki/status",
    view_func=StatusView.as_view(str("status")),
)


def get_blueprint():
    return blueprint

import ckan.lib.base as base
import ckan.lib.helpers as core_helpers
import ckan.plugins.toolkit as toolkit
from ckan.common import _, config
from flask import Blueprint, request, Response, make_response
from flask.views import MethodView
import requests

from ckanext.fuseki.backend import Reasoners, SSL_VERIFY
from ckanext.fuseki.helpers import fuseki_query_url, fuseki_service_available

log = __import__("logging").getLogger(__name__)

_WRITE_PATHS = {"update", "upload"}
_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _requires_write(service_path: str, http_method: str) -> bool:
    """Return True if this proxy request requires package_update permission."""
    path = service_path.strip("/")
    if path in _WRITE_PATHS:
        return True
    if path == "data" and http_method.upper() in _WRITE_METHODS:
        return True
    return False


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
    try:
        pkg_dict = toolkit.get_action("package_show")({}, {"id": id})
    except toolkit.ObjectNotFound:
        base.abort(404, "Dataset not found")
    except toolkit.NotAuthorized:
        base.abort(403, _("Not authorized to see this page"))

    return base.render(
        "fuseki/query.html",
        extra_vars={"pkg_dict": pkg_dict},
    )


blueprint.add_url_rule(
    "/dataset/<id>/fuseki",
    view_func=FusekiView.as_view(str("fuseki")),
    strict_slashes=False  # Handle both /fuseki and /fuseki/
)
blueprint.add_url_rule(
    "/dataset/<id>/fuseki/status",
    view_func=StatusView.as_view(str("status")),
    strict_slashes=False
)

blueprint.add_url_rule(
    "/dataset/<id>/fuseki/query",
    view_func=query_view,
    endpoint="query",
    methods=["GET"],
    strict_slashes=False
)


def fuseki_proxy(id: str, service_path: str = ''):
    """
    Transparent proxy to Fuseki with CKAN authentication.
    
    This view forwards all requests to the Fuseki dataset endpoint,
    using admin credentials to authenticate with Fuseki while checking
    CKAN permissions to ensure the user can access the dataset.
    
    URL pattern: /dataset/{id}/fuseki/$[/{service_path}]
    Forwards to: {fuseki_url}/{dataset_uuid}[/{service_path}]
    
    The $ separator prevents conflicts with existing CKAN routes like:
    - /dataset/{id}/fuseki (management UI)
    - /dataset/{id}/fuseki/status (status page)
    - /dataset/{id}/fuseki/query (redirect to query UI)
    
    Args:
        id: Dataset/package ID (can be name/slug or UUID)
        service_path: Fuseki service path (e.g., 'sparql', 'query', 'update', 'data'), empty for root
    
    Returns:
        Proxied response from Fuseki
    """
    # Fetch package to get UUID (in case id is a name/slug)
    # This also performs the permission check
    try:
        pkg_dict = toolkit.get_action('package_show')(
            {'user': toolkit.c.user or toolkit.c.author},
            {'id': id}
        )
        dataset_uuid = pkg_dict['id']  # This is always the UUID
    except toolkit.NotAuthorized:
        toolkit.abort(403, _('Not authorized to access this dataset'))
    except toolkit.ObjectNotFound:
        toolkit.abort(404, _('Dataset not found'))
    except Exception as e:
        log.error(f"Error fetching package {id}: {e}")
        toolkit.abort(500, _('Internal server error'))

    # Write operations require package_update permission
    if _requires_write(service_path, request.method):
        try:
            toolkit.check_access(
                'package_update',
                {'user': toolkit.c.user or toolkit.c.author},
                {'id': dataset_uuid},
            )
        except toolkit.NotAuthorized:
            toolkit.abort(403, _('Not authorized to modify this dataset'))

    # Get Fuseki configuration
    fuseki_url = config.get('ckanext.fuseki.url', '').rstrip('/')
    username = config.get('ckanext.fuseki.username', 'admin')
    password = config.get('ckanext.fuseki.password', 'admin')

    if not fuseki_url:
        toolkit.abort(500, _('Fuseki URL not configured'))
    
    # Build target URL - forward to Fuseki dataset endpoint using UUID
    # Fuseki datasets are created with UUID, not name
    if service_path:
        target_url = f"{fuseki_url}/{dataset_uuid}/{service_path}"
    else:
        # Root path - ensure trailing slash for Fuseki's root page
        target_url = f"{fuseki_url}/{dataset_uuid}/"
    
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
    
    log.info(f"Proxying request to Fuseki: {request.method} {target_url}")
    
    # True transparent forwarding - pass ALL headers except Host
    headers = dict(request.headers)
    # Remove Host and set it to Fuseki's host
    headers.pop('Host', None)
    
    try:
        # Forward request to Fuseki with admin credentials
        # Use stream=True and get raw response to avoid any decoding
        response = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            auth=(username, password),
            stream=True,
            verify=SSL_VERIFY,
            allow_redirects=False,
            timeout=300
        )
        
        log.info(f"Fuseki response: {response.status_code}")
        
        # Return raw response with ALL headers unchanged
        # Use response.raw to get the raw socket data without any processing
        def generate():
            for chunk in response.raw.stream(8192, decode_content=False):
                yield chunk
        
        # Use make_response to bypass CKAN's error handling and template wrapping
        flask_response = Response(
            generate(),
            status=response.status_code,
            headers=dict(response.raw.headers),  # Pass ALL headers as-is
            direct_passthrough=True  # Tell Flask not to modify the response body
        )
        
        return make_response(flask_response)
        
    except requests.exceptions.RequestException as e:
        log.error(f"Error proxying request to Fuseki: {e}")
        toolkit.abort(502, _('Bad Gateway: Could not connect to Fuseki'))


# Single route handles both root and paths
# Note: Flask's path converter doesn't match empty strings, so we need two rules
# strict_slashes=False allows both /$ and /$/ to work
blueprint.add_url_rule(
    "/dataset/<id>/fuseki/$",
    view_func=fuseki_proxy,
    endpoint="fuseki_proxy_root",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    defaults={'service_path': ''},
    strict_slashes=False
)

blueprint.add_url_rule(
    "/dataset/<id>/fuseki/$/<path:service_path>",
    view_func=fuseki_proxy,
    endpoint="fuseki_proxy",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    strict_slashes=False
)


def get_blueprint():
    return blueprint

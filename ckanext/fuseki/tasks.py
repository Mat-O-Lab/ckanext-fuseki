import datetime
import json
import os
from io import BytesIO
from urllib.parse import urljoin, urlparse, urlsplit

import ckanapi
import ckanapi.datapackage
import requests
from ckan import model
from ckan.plugins.toolkit import asbool, get_action
from requests_toolbelt.multipart.encoder import MultipartEncoder

from ckanext.fuseki import backend, db, helpers

try:
    from urllib.parse import urlsplit
except ImportError:
    from urlparse import urlsplit

import logging

# log = __import__("logging").getLogger(__name__)

CKAN_URL = os.environ.get("CKAN_SITE_URL", "http://localhost:5000")
FUSEKI_CKAN_TOKEN = os.environ.get("FUSEKI_CKAN_TOKEN", "")
SSL_VERIFY = asbool(os.environ.get("FUSEKI_SSL_VERIFY", True))
SPARQL_RES_NAME = "SPARQL"

if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()

from rq import get_current_job


def update(
    dataset_name,
    dataset_id,
    res_ids,
    callback_url,
    last_updated,
    persistant: bool = False,
    reasoning: bool = False,
    reasoner: str = "",
    unionDefaultGraph: bool = False,
    skip_if_no_changes: bool = True,
):
    # url = '{ckan}/dataset/{pkg}/resource/{res_id}/download/{filename}'.format(
    #         ckan=CKAN_URL, pkg=dataset_id, res_id=res_id, filename=res_url)
    dataset_url = f"{CKAN_URL}/dataset/{dataset_name}"
    context = {"session": model.meta.create_local_session(), "ignore_auth": True}
    metadata = {
        "ckan_url": CKAN_URL,
        "pkg_id": dataset_id,
        "resource_ids": res_ids,
        "task_created": last_updated,
        "original_url": dataset_url,
        "persistant": persistant,
        "reasoning": reasoning,
        "reasoner": reasoner,
    }
    job_info = dict()
    job_dict = dict(metadata=metadata, status="running", job_info=job_info)
    job_id = get_current_job().id
    errored = False
    db.init()

    # Set-up logging to the db
    handler = StoringHandler(job_id, job_dict)
    level = logging.DEBUG
    handler.setLevel(level)
    logger = logging.getLogger(job_id)
    # logger = logging.getLogger()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    # also show logs on stderr
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)

    callback_fuseki_hook(callback_url, api_key=FUSEKI_CKAN_TOKEN, job_dict=job_dict)
    _graph = backend.get_graph(dataset_id)
    logger.debug("{} {}".format(dataset_id, res_ids))
    if _graph:
        logger.info("Found existing graph in store: {}".format(_graph))
    else:
        _graph = backend.graph_create(
            dataset_url, dataset_id, persistant, reasoning, reasoner
        )
        logger.info("Creating graph in store: {}".format(_graph))
    # logger.debug("Creating fuseki assembly file.")
    # assembly_graph = backend.create_assembly(
    #    dataset_url, dataset_id, unionDefaultGraph=True
    # )
    # assembly_str = assembly_graph.serialize(format="turtle")
    # assembly_filename = "assembly.ttl"
    # assembly_res = resource_search(dataset_id, assembly_filename)
    # if assembly_res:
    #     logger.debug("Found existing assembly resource {}".format(assembly_res))
    #     existing_id = assembly_res["id"]
    # else:
    #     existing_id = None
    # r = file_upload(
    #     dataset_id,
    #     assembly_filename,
    #     assembly_str.encode(),
    #     res_id=existing_id,
    #     mime_type="text/turtle",
    #     authorization=FUSEKI_CKAN_TOKEN,
    # )
    logger.debug("Uploading {} to graph in store at {}".format(dataset_id, _graph))
    for res_id in res_ids:
        _res = get_action("resource_show")(context, {"id": res_id})
        try:
            backend.resource_upload(_res, _graph, api_key=FUSEKI_CKAN_TOKEN)
        except Exception as e:
            logger.error(
                "Upload {} to graph in store failed: {}".format(_res["url"], e)
            )
        else:
            logger.info("Upload {} to graph {} successfull".format(_res["url"], _graph))
    # create a link to the sparql endpoint
    link = resource_search(dataset_id, SPARQL_RES_NAME)
    if link:
        link_id = link["id"]
    else:
        link_id = None
    pkg_dict = get_action("package_show")(context, {"id": dataset_id})
    sparql_link = upload_link(
        dataset_id,
        res_id=link_id,
        mime_type="application/sparql-results+xml",
        format="SPARQL",
        authorization=FUSEKI_CKAN_TOKEN,
        link_url=helpers.fuseki_sparql_url(pkg_dict),
    )
    logger.info("SPARQL link added to dataset: {}".format(sparql_link))
    logger.info("job completed results at {}".format(_graph))
    # all is done update job status
    job_dict["status"] = "complete"
    callback_fuseki_hook(
        callback_url,
        api_key=FUSEKI_CKAN_TOKEN,
        job_dict=job_dict,
    )
    return "error" if errored else None


def get_url(action):
    """
    Get url for ckan action
    """
    if not urlsplit(CKAN_URL).scheme:
        ckan_url = "http://" + CKAN_URL.lstrip("/")
    ckan_url = CKAN_URL.rstrip("/")
    return "{ckan_url}/api/3/action/{action}".format(ckan_url=ckan_url, action=action)


def get_resource(id):
    local_ckan = ckanapi.LocalCKAN()
    try:
        res = local_ckan.action.resource_show(id=id)
    except:
        return False
    else:
        return res


def resource_search(dataset_id, res_name):
    local_ckan = ckanapi.LocalCKAN()
    dataset = local_ckan.action.package_show(id=dataset_id)
    for res in dataset["resources"]:
        if res["name"] == res_name:
            return res
    return None


def callback_fuseki_hook(result_url, api_key, job_dict):
    """Tells CKAN about the result of the fuseki (i.e. calls the callback
    function 'fuseki_hook'). Usually called by the fuseki queue job.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        if ":" in api_key:
            header, key = api_key.split(":")
        else:
            header, key = "Authorization", api_key
        headers[header] = key
    try:
        result = requests.post(
            result_url,
            data=json.dumps(job_dict, cls=DatetimeJsonEncoder),
            verify=SSL_VERIFY,
            headers=headers,
        )
    except requests.ConnectionError:
        return False

    return result.status_code == requests.codes.ok


class StoringHandler(logging.Handler):
    """A handler that stores the logging records in a database."""

    def __init__(self, task_id, input):
        logging.Handler.__init__(self)
        self.task_id = task_id
        self.input = input

    def emit(self, record):
        conn = db.ENGINE.connect()
        try:
            # Turn strings into unicode to stop SQLAlchemy
            # "Unicode type received non-unicode bind param value" warnings.
            message = str(record.getMessage())
            level = str(record.levelname)
            module = str(record.module)
            funcName = str(record.funcName)

            conn.execute(
                db.LOGS_TABLE.insert().values(
                    job_id=self.task_id,
                    timestamp=datetime.datetime.utcnow(),
                    message=message,
                    level=level,
                    module=module,
                    funcName=funcName,
                    lineno=record.lineno,
                )
            )
        except:
            pass
        finally:
            conn.close()


class DatetimeJsonEncoder(json.JSONEncoder):
    # Custom JSON encoder
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


def upload_link(
    dataset_id: str,
    link_url: str,
    res_id=None,
    group=None,
    format: str = "",
    mime_type: str = "text/html",
    # application/sparql-query
    authorization=None,
):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    if res_id:
        logging.debug("patching SPARQL link at {} to {}".format(res_id, link_url))
        url = expand_url(CKAN_URL, "/api/action/resource_patch")
        data = {
            "id": res_id,
            "url": link_url,
            "mimetype": mime_type,
            "format": format,
        }
    else:
        logging.debug("creating SPARQL link to {}".format(link_url))
        url = expand_url(CKAN_URL, "/api/action/resource_create")
        data = {
            "package_id": dataset_id,
            "url": link_url,
            "name": SPARQL_RES_NAME,
            "mimetype": mime_type,
            "format": format,
        }
    response = requests.post(url, headers=headers, json=data, verify=SSL_VERIFY)
    response.raise_for_status()
    r = response.json()
    return r


#         res = file_upload(
#             dataset_id=dataset_id,
#             filename=filename,
#             filedata=meta_data,
#             res_id=existing_id,
#             format="json-ld",
#             mime_type=mime_type,
#             authorization=CSVTOCSVW_TOKEN,
#         )


def file_upload(
    dataset_id,
    filename,
    filedata,
    res_id=None,
    format="",
    group=None,
    mime_type="text/csv",
    authorization=None,
):
    data_stream = BytesIO(filedata)
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    if res_id:
        mp_encoder = MultipartEncoder(
            fields={"id": res_id, "upload": (filename, data_stream, mime_type)}
        )
    else:
        mp_encoder = MultipartEncoder(
            fields={
                "package_id": dataset_id,
                "name": filename,
                "format": format,
                "id": res_id,
                "upload": (filename, data_stream, mime_type),
            }
        )
    headers["Content-Type"] = mp_encoder.content_type
    if res_id:
        url = expand_url(CKAN_URL, "/api/action/resource_patch")
    else:
        url = expand_url(CKAN_URL, "/api/action/resource_create")
    response = requests.post(url, headers=headers, data=mp_encoder, verify=SSL_VERIFY)
    response.raise_for_status()
    r = response.json()
    return r


def expand_url(base, url):
    p_url = urlparse(url)
    if not p_url.scheme in ["https", "http"]:
        # relative url?
        p_url = urljoin(base, p_url.path)
        return p_url
    else:
        return p_url.path.geturl()

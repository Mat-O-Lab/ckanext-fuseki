import json
import os

import ckanapi
import ckanapi.datapackage
import requests
from ckan.plugins.toolkit import get_action, asbool
from ckan import model
import datetime
from ckanext.fuseki import db, backend

try:
    from urllib.parse import urlsplit
except ImportError:
    from urlparse import urlsplit

#log = __import__("logging").getLogger(__name__)

CKAN_URL = os.environ.get("CKAN_SITE_URL", "http://localhost:5000")

SSL_VERIFY = asbool(os.environ.get("FUSEKI_SSL_VERIFY", True))
if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()

from rq import get_current_job

def update(dataset_url, dataset_id, res_ids, callback_url, last_updated, skip_if_no_changes=True):
    # url = '{ckan}/dataset/{pkg}/resource/{res_id}/download/{filename}'.format(
    #         ckan=CKAN_URL, pkg=dataset_id, res_id=res_id, filename=res_url)
    context={
        'session': model.meta.create_local_session(),
        "ignore_auth": True
        }
    metadata = {
            'ckan_url': CKAN_URL,
            'pkg_id': dataset_id,
            'resource_ids': res_ids,
            'task_created': last_updated,
            'original_url': dataset_url,
        }
    job_info=dict()
    job_dict = dict(metadata=metadata,
                    status='running',
                    job_info=job_info
    )
    job_id = get_current_job().id
    errored = False
    db.init()
    
    # Set-up logging to the db
    handler = StoringHandler(job_id, job_dict)
    level = logging.DEBUG
    handler.setLevel(level)
    logger = logging.getLogger(job_id)
    #logger = logging.getLogger()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    # also show logs on stderr
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)

    callback_fuseki_hook(callback_url,job_dict=job_dict)
    _graph = backend.get_graph(dataset_id)
    logger.debug("{} {}".format(dataset_id,res_ids))
    if _graph:
        logger.info("Found existing graph in store: {}".format(_graph))
    else:
        _graph = backend.graph_create(dataset_id)
        logger.info("Creating graph in store: {}".format(_graph))
    logger.debug("Uploading {} to graph in store at {}".format(dataset_url,_graph))
    for res_id in res_ids:
        _res = get_action("resource_show")({"ignore_auth": True}, {"id": res_id})
        try:
            backend.resource_upload(_res,_graph)
        except Exception as e:
            logger.error("Upload {} to graph in store failed: {}".format(_res['url'],e))
        else:
            logger.info("Upload {} to graph {} successfull".format(_res['url'],_graph))
    logger.info("job completed results at {}".format(_graph))
    #all is done update job status
    job_dict['status'] = 'complete'
    callback_fuseki_hook(callback_url,
                          #api_key=CSVWMAPANDTRANSFORM_TOKEN,
                          job_dict=job_dict)
    return 'error' if errored else None
    

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

def callback_fuseki_hook(result_url, job_dict):
    '''Tells CKAN about the result of the fuseki (i.e. calls the callback
    function 'fuseki_hook'). Usually called by the fuseki queue job.
    '''
    headers = {'Content-Type': 'application/json'}
    try:
        result = requests.post(
            result_url,
            data=json.dumps(job_dict, cls=DatetimeJsonEncoder),
            verify=SSL_VERIFY,
            headers=headers)
    except requests.ConnectionError:
        return False

    return result.status_code == requests.codes.ok

import logging

class StoringHandler(logging.Handler):
    '''A handler that stores the logging records in a database.'''
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

            conn.execute(db.LOGS_TABLE.insert().values(
                job_id=self.task_id,
                timestamp=datetime.datetime.utcnow(),
                message=message,
                level=level,
                module=module,
                funcName=funcName,
                lineno=record.lineno))
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
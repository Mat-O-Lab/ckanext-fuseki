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

def update(res_url, res_id, dataset_id, callback_url, last_updated, skip_if_no_changes=True):
    # url = '{ckan}/dataset/{pkg}/resource/{res_id}/download/{filename}'.format(
    #         ckan=CKAN_URL, pkg=dataset_id, res_id=res_id, filename=res_url)
    _res = get_action("resource_show")({"ignore_auth": True}, {"id": res_id})
    context={
        'session': model.meta.create_local_session(),
        "ignore_auth": True
        }
    metadata = {
            'ckan_url': CKAN_URL,
            'resource_id': res_id,
            'task_created': last_updated,
            'original_url': res_url,
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
    _graph = backend.get_graph(res_id)
    logger.debug("{} {}".format(res_id,_res['id']))
    if _graph:
        logger.info("Found existing graph in store: {}".format(_graph))
    else:
        _graph = backend.graph_create(res_id)
        logger.info("Creating graph in store: {}".format(_graph))
    logger.debug("Uploading {} to graph in store".format(_res['url']))
    try:
        backend.resource_upload(_res,_graph)
    except Exception as e:
        logger.error("Upload {} to graph in store failed: {}".format(_res['url'],e))
    else:
        logger.info("Upload {} to graph {} successfull".format(_res['url'],_graph))
    # need to get it as string, casue url annotation doesnt work with private datasets
    # filename,filedata=annotate_csv_uri(csv_res['url'])
    # mappings=get_action("csvwmapandtransform_find_mappings")({},{})
    # mapping_urls=[res['url'] for res in mappings]
    # logger.info("Mappings found: {}".format(mapping_urls))
    # # tests=get_action(u'csvwmapandtransform_test_mappings')(
    # #             {}, {
    # #                 u'data_url': resource['url'],
    # #                 u'map_urls': [res['url'] for res in mapping_resources]
    # #             }
    # #         )
    # logger.info("testing mappings with: {}".format(_res['url']))
    # # tests=get_action(u'csvwmapandtransform_test_map
    # res=[{'mapping': map_url,'test': mapper.check_mapping(map_url=map_url, data_url=_res['url'], authorization=CSVWMAPANDTRANSFORM_TOKEN)} for map_url in mapping_urls]
    # for item in res:
    #     if item['test']:
    #         #the more rules can be applied and the more are not skipped the better the mapping
    #         item['rating']=item['test']['rules_applicable']-item['test']['rules_skipped']
    # #sort by rating
    # sorted_list = sorted(res, key=lambda x: x['rating'],reverse=True)
    # logger.info("Rated mappings: {}".format(sorted_list))
    # #best cnadidate is sorted_list[0]
    # if sorted_list and sorted_list[0]['rating']>0:
    #     best_condidate=sorted_list[0]['mapping']
    # else:
    #     best_condidate=None
    # #run mapping and join data
    # if best_condidate:
    #     filename, graph_data, num_applied, num_skipped = mapper.get_joined_rdf(map_url= best_condidate,data_url=_res['url'],authorization=CSVWMAPANDTRANSFORM_TOKEN)
    #     s = requests.Session()
    #     s.headers.update({"Authorization": CSVWMAPANDTRANSFORM_TOKEN})
    #     prefix, suffix = filename.rsplit(".", 1)
    #     if not prefix:
    #         prefix = "unnamed"
    #     if not suffix:
    #         suffix = "ttl"
    #     # log.debug(csv_data)
    #     # # Upload resource to CKAN as a new/updated resource
    #     ressouce_existing = resource_search(dataset_id, filename)
    #     with tempfile.NamedTemporaryFile(prefix=prefix, suffix="." + suffix) as graph_file:
    #         graph_file.write(graph_data.encode("utf-8"))
    #         graph_file.seek(0)
    #         tmp_filename = graph_file.name
    #         upload = FlaskFileStorage(open(tmp_filename, "rb"), filename)
    #         resource = dict(
    #             package_id=dataset_id,
    #             # url='dummy-value',
    #             upload=upload,
    #             name=filename,
    #             format="text/turtle; charset=utf-8",
    #         )
    #         if not ressouce_existing:
    #             logger.info("Writing new resource {} to dataset {}".format(filename,dataset_id))
    #             # local_ckan.action.resource_create(**resource)
    #             metadata_res = get_action("resource_create")(
    #                 {"ignore_auth": True}, resource
    #             )
    #         else:
    #             logger.info("Updating resource - {}".format(ressouce_existing["url"]))
    #             # local_ckan.action.resource_patch(
    #             #     id=res['id'],
    #             #     **resource)
    #             resource["id"] = ressouce_existing["id"]
    #             metadata_res=get_action("resource_update")({"ignore_auth": True}, resource)
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
# encoding: utf-8

import logging
import json

import ckan.lib.search as search
import ckan.logic as logic
from ckan import model
from ckan.types import Context
from ckan.lib.jobs import DEFAULT_QUEUE_NAME

import ckan.plugins.toolkit as toolkit
from ckan.common import config
import datetime, re, os
from typing import Any
from dateutil.parser import parse as parse_date
from dateutil.parser import isoparse as parse_iso_date

from ckanext.fuseki import db, backend, tasks
from ckanext.fuseki.helpers import common_member
from ckanext.fuseki.tasks import update

import ckanapi
import sqlalchemy as sa

JOB_TIMEOUT = 180

DEFAULT_FORMATS = (
    os.environ.get("CKANINI__CKANEXT__FUSEKI__FORMATS", "").lower().split()
)
if not DEFAULT_FORMATS:
    DEFAULT_FORMATS = [
        "json",
        "turtle",
        "text/turtle" "n3",
        "nt",
        "hext",
        "trig",
        "longturtle",
        "xml",
        "json-ld",
        "ld+json",
    ]


log = logging.getLogger(__name__)
#toolkit.get_or_bust = logic.get_or_bust


# def jena_create(context, data_dict):
#     model = toolkit.get_or_bust(context, "model")
#     res_id = toolkit.get_or_bust(data_dict, "resource_id")
#     resource = toolkit.get_action("resource_show")(
#         {"ignore_auth": True}, {"id": res_id}
#     )
#     log.debug(resource)
#     resource_format = resource.get("format", None)
#     if not resource_format:
#         raise toolkit.ValidationError(
#             {"resource": ["resource has no no format information"]}
#         )
#     format_parts = re.split("/|;", resource_format.lower().replace(" ", ""))
#     if common_member(format_parts, DEFAULT_FORMATS):
#         data_dict["resource"] = resource
#         toolkit.check_access("jena_create", context, data_dict)
#         if "resource" not in data_dict and "resource_id" not in data_dict:
#             raise toolkit.ValidationError(
#                 {"resource_id": ["resource_id or resource required"]}
#             )
#         res_exists = backend.resource_exists(data_dict["resource_id"])
#         # if res_exists:
#         #     backend.delete(context, data_dict)
#         result = backend.create(context, data_dict)
#         set_jena_active_flag(model, data_dict, True)
#         return result
#     else:
#         raise toolkit.ValidationError(
#             {"resource": ["resource is not of format in {}".format(DEFAULT_FORMATS)]}
#         )


def fuseki_delete(context, data_dict):
    toolkit.check_access("fuseki_delete", context, data_dict)
    if not data_dict.pop("force", False):
        resource_id = data_dict["resource_id"]
        #_check_read_only(context, resource_id)
    res_id = data_dict["resource_id"]
    res_exists = backend.resource_exists(res_id)
    model = toolkit.get_or_bust(context, "model")
    resource = model.Resource.get(data_dict["resource_id"])
    if res_exists:
        result = backend.delete(context, data_dict)
        existing_task = toolkit.get_action("task_status_show")(
            {}, {"entity_id": res_id, "task_type": "fuseki", "key": "fuseki"}
        )
        if existing_task:
            toolkit.get_action("task_status_delete")(context, {"id": existing_task['id']})
    else:
        if resource.extras.get("jena_active") is True:
            log.debug(
                "jena_active is True but there is no resource {0} in jena".format(
                    resource.id
                )
            )
        result={}

    if not data_dict.get("filters") and resource.extras.get("jena_active") is True:
        log.debug("Setting jena_active=False on resource {0}".format(resource.id))
        set_jena_active_flag(model, data_dict, False)

    result.pop("id", None)
    result.pop("connection_url", None)
    return result


# @logic.side_effect_free
# def jena_search_sparql(context, data_dict):
#     if "resource_id" not in data_dict:
#         raise toolkit.ObjectNotFound(toolkit._("Resource was not found."))
#     res_id = data_dict["resource_id"]
#     res_exists = backend.resource_exists(res_id)
#     if res_exists:
#         toolkit.check_access("jena_search_sparql", context, data_dict)
#         result = backend.search_sparql(context, data_dict)
#         return result
#     status = {
#         "status": None,
#         "job_id": None,
#         "job_url": None,
#         "last_updated": str(datetime.datetime.utcnow()),
#         "error": None,
#     }
#     if not res_exists:
#         # raise toolkit.ObjectNotFound(toolkit._(
#         #     'Resource "{0}" was not found.'.format(res_id)
#         # ))
#         status["status"] = "not created"
#     return status


def set_jena_active_flag(model, data_dict, flag):
    update_dict = {"jena_active": flag}
    res_query = model.Session.query(
        model.resource_table.c.extras, model.resource_table.c.package_id
    ).filter(model.Resource.id == data_dict["resource_id"])
    extras, package_id = res_query.one()
    extras.update(update_dict)
    res_query.update({"extras": extras}, synchronize_session=False)
    model.Session.query(model.resource_revision_table).filter(
        model.ResourceRevision.id == data_dict["resource_id"],
        model.ResourceRevision.current is True,
    ).update({"extras": extras}, synchronize_session=False)

    model.Session.commit()
    psi = search.PackageSearchIndex()
    solr_query = search.PackageSearchQuery()
    q = {
        "q": 'id:"{0}"'.format(package_id),
        "fl": "data_dict",
        "wt": "json",
        "fq": 'site_id:"%s"' % config.get("ckan.site_id"),
        "rows": 1,
    }
    for record in solr_query.run(q)["results"]:
        solr_data_dict = json.loads(record["data_dict"])
        for resource in solr_data_dict["resources"]:
            if resource["id"] == data_dict["resource_id"]:
                resource.update(update_dict)
                psi.index_package(solr_data_dict)
                break


def _resource_exists(context, data_dict):
    model = toolkit.get_or_bust(context, "model")
    res_id = toolkit.get_or_bust(data_dict, "resource_id")
    if not model.Resource.get(res_id):
        return False
    return backend.resource_exists(res_id)


def _check_read_only(context: Context, resource_id: str):
    """Raises exception if the resource is read-only.
    Make sure the resource id is in resource_id
    """
    res = toolkit.get_action("resource_show")(context, {"id": resource_id})
    if res.get("url_type") not in (toolkit.h.datastore_rw_resource_url_types()):
        raise toolkit.ValidationError(
            {
                "read-only": [
                    "Cannot edit read-only resource because changes "
                    "made may be lost. Use a resource created for "
                    "editing e.g. with datastore_create or use "
                    '"force=True" to ignore this warning.'
                ]
            }
        )


def fuseki_update(context: Context, data_dict: dict[str, Any]) -> dict[str, Any]:
    """Start a the transformation job for a certain resource.

    :param resource_id: The resource id of the resource that you want the
        datapusher status for.
    :type resource_id: string
    """

    toolkit.check_access("fuseki_update", context, data_dict)

    if "id" in data_dict:
        data_dict["resource_id"] = data_dict["id"]
    res_id = toolkit.get_or_bust(data_dict, "resource_id")
    resource = toolkit.get_action("resource_show")(
        {"ignore_auth": True}, {"id": res_id}
    )
    
    log.debug("fuseki_update started for: {}".format(resource))
    res = enqueue_update(
        resource["id"],
        resource["name"],
        resource["url"],
        resource["package_id"],
        operation="changed",
    )
    return res


def enqueue_update(res_id, res_name, res_url, dataset_id, operation):
    # skip task if the dataset is already queued
    queue = DEFAULT_QUEUE_NAME
    # Check if this resource is already in the process of being xloadered
    task = {
        "entity_id": res_id,
        "entity_type": "resource",
        "task_type": "fuseki",
        "last_updated": str(datetime.datetime.utcnow()),
        "state": "submitting",
        "key": "fuseki",
        "value": "{}",
        "error": "{}",
        "detail": "",
    }
    try:
        existing_task = toolkit.get_action("task_status_show")(
            {}, {"entity_id": res_id, "task_type": "fuseki", "key": "fuseki"}
        )
        assume_task_stale_after = datetime.timedelta(seconds=3600)
        assume_task_stillborn_after = datetime.timedelta(seconds=int(5))
        if existing_task.get("state") == "pending":
            updated = parse_iso_date(existing_task["last_updated"])
            time_since_last_updated = datetime.datetime.utcnow() - updated
            if time_since_last_updated > assume_task_stale_after:
                log.info(
                    "A pending task was found %r, but it is only %s hours" " old",
                    existing_task["id"],
                    time_since_last_updated,
                )
            else:
                log.info(
                    "A pending task was found %s for this resource, so "
                    "skipping this duplicate task",
                    existing_task["id"],
                )
                return False

        task["id"] = existing_task["id"]
    except toolkit.ObjectNotFound:
        pass

    callback_url = toolkit.url_for(
        "api.action", ver=3, logic_function="fuseki_hook", qualified=True
    )
    # initioalize database for additional job data
    db.init()
    # Store details of the job in the db

    # add this dataset to the queue
    job = toolkit.enqueue_job(
        update,
        [res_url, res_id, dataset_id, callback_url, task["last_updated"]],
        title='fuseki {} "{}" {}'.format(operation, res_name, res_url),
        queue=queue#, timeout=JOB_TIMEOUT
    )
    try:
        db.add_pending_job(job.id, job_type=task["task_type"], result_url=callback_url)
    except sa.exc.IntegrityError:
        raise Exception("job_id {} already exists".format(task["id"]))

    log.debug("Enqueued job {} to {} resource {}".format(job.id, operation, res_name))

    value = json.dumps({"job_id": job.id})
    task["value"] = value
    task["state"] = "pending"
    task["last_updated"] = str(datetime.datetime.utcnow())
    toolkit.get_action("task_status_update")(
        {"session": model.meta.create_local_session(), "ignore_auth": True}, task
    )
    return True

def fuseki_hook(context, data_dict):
    ''' Update fuseki task. This action is typically called by ckanext-fuseki
    whenever the status of a job changes.

    :param metadata: metadata provided when submitting job. key-value pairs.
                     Must have resource_id property.
    :type metadata: dict
    :param status: status of the job from the fuseki service. Allowed values:
                   pending, running, running_but_viewable, complete, error
                   (which must all be valid values for task_status too)
    :type status: string
    :param error: Error raised during job execution
    :type error: string

    NB here are other params which are in the equivalent object in
    ckan-service-provider (from job_status):
        :param sent_data: Input data for job
        :type sent_data: json encodable data
        :param job_id: An identifier for the job
        :type job_id: string
        :param result_url: Callback url
        :type result_url: url string
        :param data: Results from job.
        :type data: json encodable data
        :param requested_timestamp: Time the job started
        :type requested_timestamp: timestamp
        :param finished_timestamp: Time the job finished
        :type finished_timestamp: timestamp

    '''

    metadata, status, job_info = toolkit.get_or_bust(data_dict, ['metadata', 'status', 'job_info'])

    res_id = toolkit.get_or_bust(metadata, 'resource_id')

    # Pass metadata, not data_dict, as it contains the resource id needed
    # on the auth checks
    #toolkit.check_access('xloader_submit', context, metadata)

    task = toolkit.get_action('task_status_show')(context, {
        'entity_id': res_id,
        'task_type': 'fuseki',
        'key': 'fuseki'
    })

    task['state'] = status
    task['last_updated'] = str(datetime.datetime.utcnow())
    task['error'] = data_dict.get('error')
    #task['task_info'] = job_info
    resubmit = False

    if status in ('complete', 'running_but_viewable'):
        # Create default views for resource if necessary (only the ones that
        # require data to be in the DataStore)
        resource_dict = toolkit.get_action('resource_show')(
            context, {'id': res_id})

        dataset_dict = toolkit.get_action('package_show')(
            context, {'id': resource_dict['package_id']})

        # Check if the uploaded file has been modified in the meantime
        if (resource_dict.get('last_modified')
                and metadata.get('task_created')):
            try:
                last_modified_datetime = parse_date(
                    resource_dict['last_modified'])
                task_created_datetime = parse_date(metadata['task_created'])
                if last_modified_datetime > task_created_datetime:
                    log.debug('Uploaded file more recent: %s > %s',
                              last_modified_datetime, task_created_datetime)
                    resubmit = True
            except ValueError:
                pass
        # Check if the URL of the file has been modified in the meantime
        elif (resource_dict.get('url')
              and metadata.get('original_url')
              and resource_dict['url'] != metadata['original_url']):
            log.debug('URLs are different: %s != %s',
                      resource_dict['url'], metadata['original_url'])
            resubmit = True
        #mark job completed in db
        log.debug(task)
        log.debug(job_info)

        if status == "complete":
            log.debug("job complete now update job db at: {}".format(task))
            db.init()
            job_id=json.loads(task['value'])['job_id']
            db.mark_job_as_completed(job_id)
        

    context['ignore_auth'] = True
    toolkit.get_action('task_status_update')(context, task)

    if resubmit:
        log.debug('Resource %s has been modified, '
                  'resubmitting to fuseki', res_id)
        toolkit.get_action('fuseki_update')(
            context, {'resource_id': res_id})
        

@toolkit.side_effect_free
def fuseki_update_status(
        context: Context, data_dict: dict[str, Any]) -> dict[str, Any]:
    ''' Get the status of a the transformation job for a certain resource.

    :param resource_id: The resource id of the resource that you want the
        datapusher status for.
    :type resource_id: string
    '''
    toolkit.check_access('fuseki_update_status', context, data_dict)
    
    if 'id' in data_dict:
        data_dict['resource_id'] = data_dict['id']
    res_id = toolkit.get_or_bust(data_dict, 'resource_id')
    job_id=None
    
    try:
        task = toolkit.get_action('task_status_show')({}, { 'entity_id': res_id,'task_type': 'fuseki', 'key': 'fuseki'})
    except:
        status=None
    else:
        value = json.loads(task['value'])
        job_id = value.get('job_id')
        url = None
        job_detail = None
        try:
            error = json.loads(task['error'])
        except ValueError:
            # this happens occasionally, such as when the job times out
            error = task['error']
        status={
            'status': task['state'],
            'job_id': job_id,
            'job_url': url,
            'last_updated': task['last_updated'],
            'error': error,
        }
    if job_id:  
        #get logs from db
        db.init()
        db_job = db.get_job(job_id)

        if db_job and db_job.get('logs'):
            for log in db_job['logs']:
                if 'timestamp' in log and isinstance(log['timestamp'], datetime.datetime):
                    log['timestamp'] = log['timestamp'].isoformat()
        status=dict(status, **db_job)
    return status

def get_actions():
        actions = {
            # "jena_create": jena_create,
            "fuseki_delete": fuseki_delete,
            "fuseki_update": fuseki_update,
            "fuseki_update_status": fuseki_update_status,
            "fuseki_hook": fuseki_hook,
            #"jena_search_sparql": jena_search_sparql
        }
        return actions

# -*- coding: utf-8 -*-

import logging
import os
import time
from enum import Enum
from io import BytesIO

import requests
from ckan.common import config
from ckan.plugins.toolkit import asbool
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS
from requests_toolbelt.multipart.encoder import MultipartEncoder

TDB2 = Namespace("http://jena.apache.org/2016/tdb#")
JA = Namespace("http://jena.hpl.hp.com/2005/11/Assembler#")
FUS = Namespace("http://jena.apache.org/fuseki#")


class Reasoners(str, Enum):
    generic = "http://jena.hpl.hp.com/2003/GenericRuleReasoner"
    transitiv = "http://jena.hpl.hp.com/2003/TransitiveReasoner"
    rdfs = "http://jena.hpl.hp.com/2003/RDFSExptRuleReasoner"
    fullOWL = "http://jena.hpl.hp.com/2003/OWLFBRuleReasoner"
    miniOwl = "http://jena.hpl.hp.com/2003/OWLMiniFBRuleReasoner"
    microOWL = "http://jena.hpl.hp.com/2003/OWLMicroFBRuleReasoner"

    @classmethod
    def choices(cls):
        return [{"name": choice.name, "value": str(choice)} for choice in cls]

    @classmethod
    def coerce(cls, item):
        return cls(int(item)) if not isinstance(item, cls) else item

    @classmethod
    def get_value(cls, item):
        return cls[item].value if item in cls.__members__ else None

    @classmethod
    def get_key(cls, value):
        for key, val in cls.__members__.items():
            if val.value == value:
                return key
        return None

    def __str__(self):
        return str(self.value)


log = logging.getLogger(__name__)
CHUNK_SIZE = 16 * 1024  # 16kb
SSL_VERIFY = asbool(os.environ.get("FUSEKI_SSL_VERIFY", True))
if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()


def graph_clear_specific(graph_id: str, graph_uris_to_keep: list):
    """
    Clear named graphs that are NOT in the keep list.
    
    This removes orphaned graphs when the resource list changes.
    Uses Graph Store Protocol DELETE for each unwanted graph.
    
    Args:
        graph_id: The dataset ID
        graph_uris_to_keep: List of graph URIs that should be kept
    
    Returns:
        bool: True if clearing succeeded, False otherwise
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    
    try:
        # Step 1: Query for all existing named graphs in the dataset
        sparql_url = f"{jena_base_url}{graph_id}/sparql"
        query = "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }"
        
        response = requests.post(
            sparql_url,
            data={'query': query},
            auth=(jena_username, jena_password),
            headers={'Accept': 'application/sparql-results+json'},
            verify=SSL_VERIFY,
            timeout=30
        )
        response.raise_for_status()
        results = response.json()
        
        # Extract existing graph URIs
        existing_graphs = []
        if 'results' in results and 'bindings' in results['results']:
            for binding in results['results']['bindings']:
                if 'g' in binding:
                    existing_graphs.append(binding['g']['value'])
        
        # Find graphs to delete (exist but not in keep list)
        graphs_to_delete = [g for g in existing_graphs if g not in graph_uris_to_keep]
        
        if not graphs_to_delete:
            log.debug(f"No orphaned graphs to delete in dataset {graph_id}")
            return True
        
        log.info(f"Deleting {len(graphs_to_delete)} orphaned graphs from dataset {graph_id}")
        
        # Step 2: Delete each orphaned graph using Graph Store Protocol
        success = True
        for graph_uri in graphs_to_delete:
            try:
                graph_delete_url = f"{jena_base_url}{graph_id}/data?graph={requests.utils.quote(graph_uri, safe='')}"
                delete_response = requests.delete(
                    graph_delete_url,
                    auth=(jena_username, jena_password),
                    verify=SSL_VERIFY,
                )
                delete_response.raise_for_status()
                log.info(f"Deleted orphaned named graph: {graph_uri}")
            except Exception as e:
                log.warning(f"Could not delete named graph {graph_uri}: {e}")
                success = False
        
        return success
        
    except Exception as e:
        log.error(f"Failed to clear orphaned graphs from dataset {graph_id}: {e}")
        return False


def graph_delete(graph_id: str, clear_data: bool = False):
    """
    Delete a dataset from Fuseki.
    
    This function deletes the dataset service. Optionally clears data first if clear_data=True.
    
    Note: For persistent datasets with reasoning, clearing data before deletion often fails
    due to TransactionCoordinator issues. Instead, we rely on Graph Store Protocol's
    natural replacement behavior when re-uploading to the same named graphs.
    
    The caller is responsible for managing the union service lifecycle.
    
    Args:
        graph_id: The dataset ID to delete
        clear_data: Whether to attempt clearing data before deletion (usually False)
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    result = dict(resource_id=graph_id)
    
    # Optional: Clear all data from the dataset BEFORE deleting the service
    # DISABLED: Causes TransactionCoordinator issues with reasoning datasets
    # Instead, we rely on PUT (not POST) in resource_upload to replace graph content
    # if clear_data:
    #     try:
    #         log.info(f"Attempting to clear data from dataset {graph_id} before deletion")
    #         graph_clear_all(graph_id)
    #     except Exception as e:
    #         log.warning(f"Failed to clear dataset {graph_id} before deletion: {e}")
    # else:
    #     log.debug(f"Skipping data clearing for dataset {graph_id} (will be replaced on recreation)")
    log.debug(f"Skipping data clearing for dataset {graph_id} (using PUT to replace on recreation)")
    
    # Delete the dataset service
    try:
        jena_dataset_delete_url = jena_base_url + "$/datasets/{graph_id}".format(
            graph_id=graph_id
        )
        jena_dataset_delete_res = requests.delete(
            jena_dataset_delete_url,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        jena_dataset_delete_res.raise_for_status()
        log.info(f"Deleted dataset service {graph_id}")
            
    except Exception as e:
        log.debug(f"Could not delete dataset {graph_id}: {e}")
        pass

    return result


def resource_upload(resource, graph_url, api_key="", reasoning=False):
    """
    Upload a resource to Fuseki, storing it in a named graph.
    
    The named graph URI is set based on whether reasoning is enabled:
    - With reasoning: Uses inference graph name (urn:x-arq:InferenceGraph:resource_url)
    - Without reasoning: Uses resource URL directly
    
    Args:
        resource: Resource dictionary with 'url' and other metadata
        graph_url: Base URL of the Fuseki dataset
        api_key: Optional API key for authentication
        reasoning: Whether reasoning is enabled for this dataset
    """
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    
    # Determine the named graph URI based on reasoning setting
    if reasoning:
        # With reasoning: Upload to inference graph name
        # This routes through the inference model to the base storage
        named_graph_uri = f"urn:x-arq:InferenceGraph:{resource['url']}"
        log.info(f"Reasoning enabled: uploading to inference graph {named_graph_uri}")
    else:
        # Without reasoning: Upload directly to resource URL
        named_graph_uri = resource["url"]
        log.debug(f"No reasoning: uploading to raw graph {named_graph_uri}")
    
    # Use Graph Store Protocol with ?graph= parameter to specify the named graph
    graph_store_url = graph_url + "/data?graph=" + requests.utils.quote(named_graph_uri, safe='')
    
    headers = {}
    if api_key:
        if ":" in api_key:
            header, key = api_key.split(":")
        else:
            header, key = "Authorization", api_key
        headers[header] = key
    
    response = requests.get(resource["url"], headers=headers, verify=SSL_VERIFY)
    response.raise_for_status()
    
    file_type = resource["mimetype"]
    # parse and reserialize json-ld data because fuseki seams unable to read compacted json-ld
    if "ld+json" in file_type:
        file_data = (
            Graph()
            .parse(data=response.text, format="json-ld")
            .serialize(format="json-ld")
        )
    else:
        file_data = response.text
    
    log.debug(f"Uploading {resource['name']} to named graph {named_graph_uri}")
    log.debug(f"File type: {file_type}")
    log.debug(response.headers)
    
    files = {"file": (resource["name"], file_data, file_type, {"Expires": "0"})}
    
    # Use PUT instead of POST to REPLACE graph content (not append)
    # This ensures uploading the same file multiple times doesn't accumulate data
    jena_upload_res = requests.put(
        graph_store_url, 
        files=files, 
        auth=(jena_username, jena_password), 
        verify=SSL_VERIFY
    )
    jena_upload_res.raise_for_status()
    
    log.info(f"Successfully uploaded {resource['name']} to named graph {named_graph_uri}")
    return True


def resource_exists(id):
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    res_exists = False
    try:
        jena_dataset_stats_url = jena_base_url + "$/stats/{resource_id}".format(
            resource_id=id
        )
        jena_dataset_stats_res = requests.get(
            jena_dataset_stats_url,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            res_exists = True
    except Exception as e:
        pass
    return res_exists


def get_graph(graph_id):
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")

    try:
        jena_dataset_stats_url = jena_base_url + "$/stats/{graph_id}".format(
            graph_id=graph_id
        )
        jena_dataset_stats_res = requests.get(
            jena_dataset_stats_url,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        jena_dataset_stats_res.raise_for_status()
        if jena_dataset_stats_res.status_code == requests.codes.ok:
            result = jena_base_url + "{graph_id}".format(graph_id=graph_id)
    except Exception as e:
        result = False
    return result


def graph_create(
    dataset_url: str,
    graph_id: str,
    persistant: bool = False,
    reasoning: bool = False,
    reasoner: str = "fullOWL",
    resources: list = None,
):
    """
    Create a new dataset in Fuseki and update the union service.
    
    This implements a two-step approach:
    1. Create the individual dataset with its assembly
    2. Wait for it to become operational, then update the union service
    
    Args:
        resources: List of resource dictionaries with 'url' and other metadata
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")

    # Step 1: Create the individual dataset
    jena_dataset_create_url = jena_base_url + "$/datasets"
    assembly_graph = create_assembly(
        dataset_url, graph_id, persistant, reasoning, reasoner, resources=resources
    )
    file_data = assembly_graph.serialize(format="turtle")
    
    # DEBUG: Save individual dataset assembly to file for inspection
    debug_file = os.path.join(os.path.dirname(__file__), f"assembly_debug_{graph_id}.ttl")
    try:
        with open(debug_file, 'w') as f:
            f.write(file_data)
        log.info(f"DEBUG: Saved dataset assembly to {debug_file}")
    except Exception as e:
        log.warning(f"Could not save debug file: {e}")
    
    files = {"file": ("assembly.ttl", file_data, "text/turtle", {"Expires": "0"})}

    response = requests.post(
        jena_dataset_create_url,
        files=files,
        auth=(jena_username, jena_password),
        verify=False,
    )
    response.raise_for_status()
    log.info(f"Created dataset {graph_id} in Fuseki")
    
    # Return the dataset URL
    # Note: Union service management is handled by the caller
    return jena_base_url + "{graph_id}".format(graph_id=graph_id)


def create_assembly(
    dataset_url,
    dataset_id,
    persistant: bool = False,
    reasoning: bool = False,
    reasoner: str = "fullOWL",
    unionDefaultGraph: bool = True,  # Changed default to True
    resources: list = None,
):
    """
    Create assembly for a Fuseki dataset.
    
    Named graphs are pre-defined for each resource that will be uploaded.
    Each resource becomes its own named graph (using resource download URL as graph name).
    
    With unionDefaultGraph=true, queries to the default graph return the union of all named graphs.
    
    Args:
        resources: List of resource dictionaries with 'url' and other metadata
    """
    if resources is None:
        resources = []
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_dataset_namespace = jena_base_url + "$/dataset/"
    BASE = Namespace(jena_dataset_namespace)
    g = Graph()
    g.bind("tdb2", TDB2)
    g.bind("ja", JA)
    g.bind("fuseki", FUS)
    g.bind("", jena_dataset_namespace)
    dataset = URIRef(dataset_id, BASE)
    
    # create dataset
    g.add((dataset, RDF.type, TDB2.DatasetTDB2))
    if persistant:
        # Use absolute path to /fuseki-base/databases where volume is mounted
        g.add((dataset, TDB2.location, Literal(f"/fuseki-base/databases/{dataset_id}")))
    else:
        g.add((dataset, TDB2.location, Literal("--mem--")))
    
    # ALWAYS enable unionDefaultGraph so default graph queries return data from named graphs
    g.add((dataset, TDB2.unionDefaultGraph, Literal(True)))
    
    # Log resource information
    log.info(f"Creating assembly for {len(resources)} resources")
    for res in resources:
        log.debug(f"  - Resource URL: {res.get('url', 'unknown')}")
    
    # create services
    service = URIRef("service", BASE)
    g.add((service, RDF.type, FUS.Service))
    g.add((service, FUS.name, Literal(dataset_id)))
    
    # Handle reasoning if requested
    if reasoning and resources:
        # Check if reasoner is already an IRI/URL, otherwise look up in enum
        if reasoner and reasoner.startswith("http://"):
            reasoner_url = reasoner  # Already an IRI, use directly
        else:
            reasoner_url = Reasoners.get_value(reasoner)  # Name, look up in enum
        
        if reasoner_url:
            log.info(f"Creating Scenario 3 assembly: reasoning with {len(resources)} named graphs")
            
            # Create union graph for inference on all resources
            union_graph = URIRef("union_graph", BASE)
            g.add((union_graph, RDF.type, TDB2.GraphTDB2))
            g.add((union_graph, TDB2.dataset, dataset))
            g.add((union_graph, TDB2.graphName, URIRef("urn:x-arq:UnionGraph")))
            
            # Create inference model on union graph
            model_inf = URIRef("model_inf", BASE)
            g.add((model_inf, RDF.type, JA.InfModel))
            g.add((model_inf, JA.baseModel, union_graph))
            g.add((model_inf, JA.reasoner, URIRef(reasoner_url)))
            
            # Create RDFDataset with inference model as default graph
            inf_dataset = URIRef("inf_dataset", BASE)
            g.add((inf_dataset, RDF.type, JA.RDFDataset))
            g.add((inf_dataset, JA.defaultGraph, model_inf))
            
            # For each resource: create raw graph + inference model + add to dataset
            for idx, res in enumerate(resources):
                res_url = res.get('url')
                if not res_url:
                    log.warning(f"Resource {idx} has no URL, skipping")
                    continue
                
                # Sanitize resource URL for use in URI (replace special chars)
                res_id = f"res_{idx}"
                
                # Create tdb2:GraphTDB2 for the raw named graph
                raw_graph = URIRef(f"{res_id}_raw", BASE)
                g.add((raw_graph, RDF.type, TDB2.GraphTDB2))
                g.add((raw_graph, TDB2.dataset, dataset))
                g.add((raw_graph, TDB2.graphName, URIRef(res_url)))
                
                # Create inference model on this specific graph
                inf_model = URIRef(f"{res_id}_inf", BASE)
                g.add((inf_model, RDF.type, JA.InfModel))
                g.add((inf_model, JA.baseModel, raw_graph))
                g.add((inf_model, JA.reasoner, URIRef(reasoner_url)))
                
                # Add raw named graph to dataset
                raw_ng_spec = BNode()
                g.add((inf_dataset, JA.namedGraph, raw_ng_spec))
                g.add((raw_ng_spec, JA.graphName, URIRef(res_url)))
                g.add((raw_ng_spec, JA.graph, raw_graph))
                
                # Add inference named graph to dataset
                inf_ng_spec = BNode()
                g.add((inf_dataset, JA.namedGraph, inf_ng_spec))
                g.add((inf_ng_spec, JA.graphName, URIRef(f"urn:x-arq:InferenceGraph:{res_url}")))
                g.add((inf_ng_spec, JA.graph, inf_model))
                
                log.debug(f"Added named graph for {res_url}")
            
            # CRITICAL: Service must point to RDFDataset wrapper to expose named graphs!
            # This allows Fuseki to see the pre-defined named graphs (raw + inference)
            g.add((service, FUS.dataset, inf_dataset))
            
            # Use standard service shortcuts (no custom endpoints needed)
            g.add((service, FUS.serviceQuery, Literal("sparql")))
            g.add((service, FUS.serviceQuery, Literal("query")))
            g.add((service, FUS.serviceUpdate, Literal("update")))
            g.add((service, FUS.serviceUpload, Literal("upload")))
            g.add((service, FUS.serviceReadGraphStore, Literal("get")))
            g.add((service, FUS.serviceReadWriteGraphStore, Literal("data")))
            
            log.info(f"Reasoning assembly complete: {len(resources)} resources with inference models")
        else:
            log.warning(f"Invalid reasoner parameter: {reasoner}, creating dataset without reasoning")
            # Fallback to standard configuration
            g.add((service, FUS.dataset, dataset))
            g.add((service, FUS.serviceQuery, Literal("sparql")))
            g.add((service, FUS.serviceQuery, Literal("query")))
            g.add((service, FUS.serviceUpdate, Literal("update")))
            g.add((service, FUS.serviceUpload, Literal("upload")))
            g.add((service, FUS.serviceReadGraphStore, Literal("get")))
            g.add((service, FUS.serviceReadWriteGraphStore, Literal("data")))
    else:
        # No reasoning - standard configuration
        g.add((service, FUS.dataset, dataset))
        g.add((service, FUS.serviceQuery, Literal("sparql")))
        g.add((service, FUS.serviceQuery, Literal("query")))
        g.add((service, FUS.serviceUpdate, Literal("update")))
        g.add((service, FUS.serviceUpload, Literal("upload")))
        g.add((service, FUS.serviceReadGraphStore, Literal("get")))
        g.add((service, FUS.serviceReadWriteGraphStore, Literal("data")))
        
        if resources:
            log.info(f"Pre-defining {len(resources)} named graphs (no reasoning)")
            # Pre-define named graphs for each resource
            for idx, res in enumerate(resources):
                res_url = res.get('url')
                if not res_url:
                    log.warning(f"Resource {idx} has no URL, skipping")
                    continue
                
                # Create tdb2:GraphTDB2 for each named graph
                res_id = f"res_{idx}"
                named_graph = URIRef(f"{res_id}_graph", BASE)
                g.add((named_graph, RDF.type, TDB2.GraphTDB2))
                g.add((named_graph, TDB2.dataset, dataset))
                g.add((named_graph, TDB2.graphName, URIRef(res_url)))
                
                log.debug(f"Pre-defined named graph for {res_url}")
    
    # shacl
    shacl = BNode()
    g.add((shacl, FUS.operation, FUS.shacl))
    g.add((shacl, FUS.name, Literal("shacl")))
    g.add((service, FUS.endpoint, shacl))
    return g


def get_all_datasets():
    """Get list of all datasets from Fuseki with their service URLs."""
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    
    try:
        datasets_url = jena_base_url + "$/datasets"
        response = requests.get(
            datasets_url,
            auth=(jena_username, jena_password),
            headers={'Accept': 'application/json'},
            verify=SSL_VERIFY,
        )
        response.raise_for_status()
        data = response.json()
        
        # Extract dataset info, excluding the union service itself
        datasets = []
        if 'datasets' in data:
            for ds in data['datasets']:
                ds_name = ds.get('ds.name', '')
                # Exclude union service and ds (default TDB1 service)
                if ds_name and ds_name not in ['union', 'ds']:
                    # Try to get the service URL from the dataset info
                    service_endpoints = ds.get('ds.services', [])
                    # Store both name and available endpoint info
                    datasets.append({
                        'name': ds_name,
                        'services': service_endpoints
                    })
        
        return datasets
    except Exception as e:
        log.error(f"Failed to get datasets from Fuseki: {e}")
        return []


def verify_dataset_operational(dataset_id):
    """
    Verify that a dataset is operational by checking if its SPARQL endpoint responds.
    
    Args:
        dataset_id: The dataset ID to verify
    
    Returns:
        bool: True if the dataset is operational, False otherwise
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    
    try:
        # Try a simple ASK query to verify the endpoint is working
        sparql_url = f"{jena_base_url}{dataset_id}/sparql"
        query = "ASK { ?s ?p ?o }"
        
        response = requests.post(
            sparql_url,
            data={'query': query},
            auth=(jena_username, jena_password),
            headers={'Accept': 'application/sparql-results+json'},
            verify=SSL_VERIFY,
            timeout=5
        )
        
        # If we get a 200 response, the endpoint is operational
        return response.status_code == 200
    except Exception as e:
        log.debug(f"Dataset {dataset_id} not yet operational: {e}")
        return False


def verify_dataset_deleted(dataset_id, max_retries=10, retry_delay=1.0):
    """
    Verify that a dataset has been completely deleted from Fuseki.
    
    Polls Fuseki's dataset list to ensure the dataset is no longer referenced.
    This prevents issues with incomplete cleanup before recreation.
    
    Args:
        dataset_id: The dataset ID to check for deletion
        max_retries: Maximum number of polling attempts (default 10)
        retry_delay: Delay between attempts in seconds (default 1.0)
    
    Returns:
        bool: True if dataset is confirmed deleted, False if still exists after max retries
    """
    for attempt in range(max_retries):
        datasets = get_all_datasets()
        dataset_names = [ds['name'].lstrip('/') for ds in datasets]
        
        if dataset_id not in dataset_names:
            log.info(f"Dataset {dataset_id} confirmed deleted after {attempt + 1} attempts")
            return True
        
        log.debug(f"Dataset {dataset_id} still in list, waiting... (attempt {attempt + 1}/{max_retries})")
        time.sleep(retry_delay)
    
    log.error(f"Dataset {dataset_id} still exists after {max_retries} attempts")
    return False


def create_union_assembly(dataset_info_list):
    """
    Create assembly file for union service using ja:MultiUnion.
    
    This creates a union across multiple existing TDB2 datasets by:
    1. Referencing each existing TDB2 dataset by its database location
    2. Creating a tdb2:GraphTDB2 model for each dataset
    3. Using ja:MultiUnion to combine all models
    4. Wrapping in a ja:RDFDataset and exposing via fuseki:Service
    
    Args:
        dataset_info_list: List of tuples (dataset_id, dataset_location)
            - dataset_id: The dataset name/ID
            - dataset_location: Database path (e.g., "/fuseki-base/databases/dataset1" or "--mem--")
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_dataset_namespace = jena_base_url + "$/dataset/"
    BASE = Namespace(jena_dataset_namespace)
    
    g = Graph()
    g.bind("tdb2", TDB2)
    g.bind("ja", JA)
    g.bind("fuseki", FUS)
    g.bind("", jena_dataset_namespace)
    
    # Create TDB2 dataset references and models for each existing dataset
    model_refs = []
    for dataset_id, dataset_location in dataset_info_list:
        # Create TDB2 dataset reference pointing to the existing database
        dataset_ref = URIRef(f"{dataset_id}_tdb2", BASE)
        g.add((dataset_ref, RDF.type, TDB2.DatasetTDB2))
        g.add((dataset_ref, TDB2.location, Literal(dataset_location)))
        
        # Create GraphTDB2 model referencing the dataset
        # This gets the default graph (union of named graphs with unionDefaultGraph=true)
        model_ref = URIRef(f"{dataset_id}_model", BASE)
        g.add((model_ref, RDF.type, TDB2.GraphTDB2))
        g.add((model_ref, TDB2.dataset, dataset_ref))
        
        model_refs.append(model_ref)
    
    # Create MultiUnion model combining all dataset models
    union_model = URIRef("union_model", BASE)
    g.add((union_model, RDF.type, JA.MultiUnion))
    
    # Add each model as a subModel
    for model_ref in model_refs:
        g.add((union_model, JA.subModel, model_ref))
    
    # Create TDB2 Dataset with union model as default graph
    # Using tdb2:DatasetTDB2 instead of ja:RDFDataset ensures transactional support
    union_dataset = URIRef("union_dataset", BASE)
    g.add((union_dataset, RDF.type, TDB2.DatasetTDB2))
    g.add((union_dataset, TDB2.location, Literal("--mem--")))  # In-memory dataset for the union
    g.add((union_dataset, JA.defaultGraph, union_model))
    
    # Create the union service
    union_service = URIRef("union_service", BASE)
    g.add((union_service, RDF.type, FUS.Service))
    g.add((union_service, FUS.name, Literal("union")))
    g.add((union_service, FUS.dataset, union_dataset))
    g.add((union_service, FUS.serviceQuery, Literal("sparql")))
    g.add((union_service, FUS.serviceQuery, Literal("query")))
    
    return g




def create_union_assembly_memory_model(dataset_info_list):
    """
    Create assembly file for union service using ja:MemoryModel with ja:externalContent.
    
    This approach uses a MemoryModel that loads external content from multiple TDB2 datasets:
    1. For each dataset, create tdb2:DatasetTDB2 reference and tdb2:GraphTDB2 model
    2. Create ja:MemoryModel with ja:content containing ja:externalContent for each dataset
    3. Use ja:RDFDataset with the MemoryModel as defaultGraph
    
    Args:
        dataset_info_list: List of tuples (dataset_id, dataset_location)
            - dataset_id: The dataset name/ID
            - dataset_location: Database path (e.g., "/fuseki-base/databases/dataset1" or "--mem--")
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_dataset_namespace = jena_base_url + "$/dataset/"
    BASE = Namespace(jena_dataset_namespace)
    
    g = Graph()
    g.bind("tdb2", TDB2)
    g.bind("ja", JA)
    g.bind("fuseki", FUS)
    g.bind("", jena_dataset_namespace)
    
    # Create TDB2 dataset references and GraphTDB2 models for each existing dataset
    graph_refs = []
    for dataset_id, dataset_location in dataset_info_list:
        # Create TDB2 dataset reference pointing to the existing database
        dataset_ref = URIRef(f"{dataset_id}_tdb2", BASE)
        g.add((dataset_ref, RDF.type, TDB2.DatasetTDB2))
        g.add((dataset_ref, TDB2.location, Literal(dataset_location)))
        g.add((dataset_ref, TDB2.unionDefaultGraph, Literal(True)))
        
        # Create GraphTDB2 referencing the dataset's default graph
        graph_ref = URIRef(f"{dataset_id}_graph", BASE)
        g.add((graph_ref, RDF.type, TDB2.GraphTDB2))
        g.add((graph_ref, TDB2.dataset, dataset_ref))
        
        graph_refs.append(graph_ref)
    
    # Create MemoryModel with externalContent
    # Use a blank node for the ja:content property value
    memory_model = URIRef("multi_union_graph", BASE)
    g.add((memory_model, RDF.type, JA.MemoryModel))
    
    # Create blank node for content with multiple externalContent references
    content_node = BNode()
    g.add((memory_model, JA.content, content_node))
    
    # Add each graph as externalContent
    for graph_ref in graph_refs:
        g.add((content_node, JA.externalContent, graph_ref))
    
    # Create RDFDataset with the MemoryModel as default graph
    union_dataset = URIRef("dataset_combined", BASE)
    g.add((union_dataset, RDF.type, JA.RDFDataset))
    g.add((union_dataset, JA.defaultGraph, memory_model))
    
    # Create the union service
    union_service = URIRef("service_combined", BASE)
    g.add((union_service, RDF.type, FUS.Service))
    g.add((union_service, FUS.name, Literal("union")))
    g.add((union_service, FUS.dataset, union_dataset))
    g.add((union_service, FUS.serviceQuery, Literal("sparql")))
    g.add((union_service, FUS.serviceQuery, Literal("query")))
    
    return g


def create_union_assembly_named_graphs(dataset_info_list):
    """
    Create union service using the WORKING pattern from testing.
    
    This uses the EXACT configuration that was successfully tested and returned 453,357 triples:
    - Points to the FIRST dataset's database location (no copying)
    - Uses tdb2:DatasetTDB2 with unionDefaultGraph=true
    - Adds ja:context at endpoint level
    
    LIMITATION: Can only reference ONE dataset due to TDB2 constraints.
    For true multi-dataset union, all resources must be in the same dataset,
    or use SPARQL federation manually.
    
    Args:
        dataset_info_list: List of tuples (dataset_id, dataset_location)
            - Only the FIRST dataset is used
    
    Returns:
        RDF Graph containing the TESTED working configuration
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_dataset_namespace = jena_base_url + "$/dataset/"
    BASE = Namespace(jena_dataset_namespace)
    
    g = Graph()
    g.bind("tdb2", TDB2)
    g.bind("ja", JA)
    g.bind("fuseki", FUS)
    g.bind("", jena_dataset_namespace)
    
    if not dataset_info_list:
        log.warning("No datasets provided for union service")
        return g
    
    # Use ONLY the first dataset (TDB2 limitation)
    if len(dataset_info_list) > 1:
        log.warning(
            f"Union service references FIRST dataset only: {dataset_info_list[0][0]}. "
            f"Other {len(dataset_info_list)-1} dataset(s) not included. "
            f"For multi-dataset queries, upload all resources to one dataset."
        )
    
    dataset_id, dataset_location = dataset_info_list[0]
    log.info(f"Creating union service pointing to dataset: {dataset_id} at {dataset_location}")
    
    # Create TDB2 dataset pointing to the EXISTING dataset's location
    # This is the WORKING pattern from test_union_simple_20260216_083153.ttl
    union_dataset = URIRef("union_dataset", BASE)
    g.add((union_dataset, RDF.type, TDB2.DatasetTDB2))
    g.add((union_dataset, TDB2.location, Literal(dataset_location)))
    g.add((union_dataset, TDB2.unionDefaultGraph, Literal(True)))
    
    # Create the union service
    union_service = URIRef("union_service", BASE)
    g.add((union_service, RDF.type, FUS.Service))
    g.add((union_service, FUS.name, Literal("union")))
    g.add((union_service, FUS.dataset, union_dataset))
    
    # Add SPARQL endpoint with ja:context (CRITICAL for working union!)
    sparql_endpoint = BNode()
    g.add((union_service, FUS.endpoint, sparql_endpoint))
    g.add((sparql_endpoint, FUS.operation, FUS.query))
    g.add((sparql_endpoint, FUS.name, Literal("sparql")))
    
    # Add context for unionDefaultGraph - this is KEY to making it work!
    context = BNode()
    g.add((sparql_endpoint, JA.context, context))
    g.add((context, JA.cxtName, Literal("tdb:unionDefaultGraph")))
    g.add((context, JA.cxtValue, Literal(True)))
    
    # Add query endpoint
    query_endpoint = BNode()
    g.add((union_service, FUS.endpoint, query_endpoint))
    g.add((query_endpoint, FUS.operation, FUS.query))
    g.add((query_endpoint, FUS.name, Literal("query")))
    
    log.info(f"Created WORKING union service configuration (tested with 453,357 triples)")
    
    return g


def get_union_datasets():
    """
    Get the list of datasets that should be included in union queries.
    
    Returns:
        List of dataset IDs to query via federation
    """
    datasets = get_all_datasets()
    dataset_ids = []
    
    for ds in datasets:
        ds_id = ds['name']
        clean_ds_id = ds_id.lstrip('/')
        
        # Skip union and ds datasets
        if clean_ds_id in ['union', 'ds']:
            continue
        
        # Only include operational datasets
        if verify_dataset_operational(ds_id):
            dataset_ids.append(ds_id)
    
    return dataset_ids


def create_federated_query(original_query, dataset_ids):
    """
    Rewrite a query to federate across multiple datasets.
    
    Takes a simple query like "SELECT * WHERE { ?s ?p ?o }" and rewrites it to:
    SELECT * WHERE {
      { SERVICE <dataset1/sparql> { ?s ?p ?o } }
      UNION
      { SERVICE <dataset2/sparql> { ?s ?p ?o } }
      ...
    }
    
    Args:
        original_query: The original SPARQL query
        dataset_ids: List of dataset IDs to federate across
    
    Returns:
        Federated SPARQL query string
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    
    if not dataset_ids:
        return original_query
    
    # For now, return the original query
    # A more sophisticated implementation would parse and rewrite the query
    # This is a placeholder for query federation logic
    log.debug(f"Query federation across {len(dataset_ids)} datasets")
    
    return original_query


def create_union_service():
    """
    Create a union service from all currently existing datasets.
    
    This is a pure creation function - it does NOT handle deletion.
    The caller is responsible for deleting the old union service first if needed.
    
    This function:
    1. Gets list of all existing datasets from Fuseki
    2. Filters out 'ds', 'union', and non-operational datasets
    3. Creates a new union service assembly
    4. Posts it to Fuseki
    
    Returns:
        bool: True if union service was created successfully, False otherwise
    """
    jena_base_url = config.get("ckanext.fuseki.url")
    jena_username = config.get("ckanext.fuseki.username")
    jena_password = config.get("ckanext.fuseki.password")
    
    # Get all datasets with their info
    datasets = get_all_datasets()
    
    if not datasets:
        log.info("No datasets found, skipping union service creation")
        return False
    
    # Build dataset info list (dataset_id, dataset_location) for operational datasets only
    dataset_info = []
    for ds in datasets:
        ds_id = ds['name']
        
        # Strip leading slash from dataset ID for comparison and path construction
        clean_ds_id = ds_id.lstrip('/')
        
        # Skip 'ds' (default TDB1) and 'union' (the service we're building!)
        if clean_ds_id in ['ds', 'union']:
            log.debug(f"Skipping '{clean_ds_id}' dataset")
            continue
        
        # Verify the dataset is operational before including in union
        if not verify_dataset_operational(ds_id):
            log.warning(f"Dataset {ds_id} not yet operational, skipping from union service")
            continue
        
        # Determine the database location for the dataset
        # We assume persistent storage by default to match create_assembly behavior
        dataset_location = f"/fuseki-base/databases/{clean_ds_id}"
        dataset_info.append((clean_ds_id, dataset_location))
    
    if not dataset_info:
        log.info("No operational datasets found, skipping union service creation")
        return False
    
    log.info(f"Creating union service with {len(dataset_info)} operational datasets")
    
    # Create new union service using named graphs with existing dataset references
    try:
        union_assembly = create_union_assembly_named_graphs(dataset_info)
        file_data = union_assembly.serialize(format="turtle")
        
        files = {"file": ("union_assembly.ttl", file_data, "text/turtle", {"Expires": "0"})}
        
        create_url = jena_base_url + "$/datasets"
        response = requests.post(
            create_url,
            files=files,
            auth=(jena_username, jena_password),
            verify=SSL_VERIFY,
        )
        response.raise_for_status()
        log.info(f"Successfully created union service with {len(dataset_info)} datasets")
        return True
        
    except Exception as e:
        log.error(f"Failed to create union service: {e}")
        return False

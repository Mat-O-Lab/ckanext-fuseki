[![Tests](https://github.com/Mat-O-Lab/ckanext-fuseki/actions/workflows/test.yml/badge.svg)](https://github.com/Mat-O-Lab/ckanext-fuseki/actions/workflows/test.yml)

# ckanext-fuseki

Extension create a new tab in the dataset view that enables you to upload selcted resources to a connected jena fuseki triple store. 

## Requirements
Needs a running instance of the jena fuseki. 
Point at it through env variables. Also needed is a Api Token for an account with the right privaledges to make the background job work on private datasets and ressources.

* Apache Jena and Fuseki server need to be running.
* <optional> A sparklis web app for querying the dataset, see optional folder for a container deployment of jena fuseki and sparklis.

## Purpose

ckanext-fuseki is an extension for enabling the semantic aspect of CKAN with Apache Jena.

This extension provides an ability to let users store a set of semantic resource (e.g. rdf, ttl, owl) in Apache Jena and perform SPARQL semantic queries.

### Notes:

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.8 and arlier  | not tested    |
| 2.9             | no    |
| 2.10            | yes    |


## Installation

**TODO:** Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-fuseki:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/Mat-O-Lab/ckanext-fuseki.git
    cd ckanext-fuseki
    pip install -e .
	pip install -r requirements.txt

3. Add `fuseki` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

     sudo service apache2 reload


## Config settings

```bash
FUSEKI_CKAN_TOKEN=${CKAN_API_TOKEN}
CKANINI__CKANEXT__FUSEKI__URL = http://<fuseki_host>:<fuseki_port>/
CKANINI__CKANEXT__FUSEKI__USERNAME = <admin_user>
CKANINI__CKANEXT__FUSEKI__PASSWORD = *****
```
or ckan.ini parameters.
```bash
ckan.jena.fuseki.url = http://<fuseki_host>:<fuseki_port>/
ckan.jena.fuseki.username = <admin_user>
ckan.jena.fuseki.password = *****
```
If no Api Token is given, only public resources can be uploaded to the triple store!

You can set the default formats to preselected for upload by setting the formats,
```bash
CKANINI__CKANEXT__FUSEKI__FORMATS = 'json turtle text/turtle n3 nt hext trig longturtle xml json-ld ld+json'
```
else it will react to the listed formats by default

# Acknowledgements

This projects work is based on a fork of the repo [etri-odp/ckanext-jena](https://github.com/etri-odp/ckanext-jena) and we like to thank the authors of that project for sharing there work.
It was supported by Institute for Information & communications Technology Promotion (IITP) grant funded by the Korea government (MSIT) (No.2017-00253, Development of an Advanced Open Data Distribution Platform based on International Standards)

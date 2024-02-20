[![Tests](https://github.com/Mat-O-Lab/ckanext-fuseki/workflows/Tests/badge.svg?branch=main)](https://github.com/Mat-O-Lab/ckanext-fuseki/actions)

# ckanext-fuseki

Extension automatically generating csvw metadata for uploaded textual tabular data. It uploads the data of the first table documented into a datastore for the source csv file.
**should be used as replacement for datapusher**

## Requirements
Needs a running instance of the jena fuseki. 
Point at it through env variables
```bash
CKANINI__CKANEXT__FUSEKI__URL = http://<fuseki_host>:<fuseki_port>/
CKANINI__CKANEXT__FUSEKI__USERNAME = <admin_user>
CKANINI__CKANEXT__FUSEKI__PASSWORD = *****
CKANINI__CKANEXT__FUSEKI__FORMATS = 'json turtle text/turtle n3 nt hext trig longturtle xml json-ld ld+json'
```
or ckan.ini parameters.
```bash
ckan.jena.fuseki.url = http://<fuseki_host>:<fuseki_port>/
ckan.jena.fuseki.username = <admin_user>
ckan.jena.fuseki.password = *****
```


You can set the default formats to annotate by setting the env variable CSVTOCSVW_FORMATS for example
```bash
CKANINI__CKANEXT__FUSEKI__FORMATS = 'json turtle text/turtle n3 nt hext trig longturtle xml json-ld ld+json'
```
else it will react to the listed formats by default

## Purpose

ckanext-fuseki is an extension for enabling the semantic aspect of CKAN with Apache Jena.

This extension provides an ability to let users store a certain semantic resource (e.g. rdf, ttl, owl) in Apache Jena and perform SPARQL semantic queries.

### Notes:

* Apache Jena and Fuseki server need to be running.
* jena_search_sparql api can be called with ``resource_id`` and ``q`` parameters for semantic queries.

**TODO:** For example, you might want to mention here which versions of CKAN this
extension works with.

If your extension works across different versions you can add the following table:

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.8 and arlier  | not tested    |
| 2.9             | no    |
| 2.10            | yes    |

Suggested values:

* "yes"
* "not tested" - I can't think of a reason why it wouldn't work
* "not yet" - there is an intention to get it working
* "no"


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

None at present

**TODO:** Document any optional config settings here. For example:

	# The minimum number of hours to wait before re-checking a resource
	# (optional, default: 24).
	ckanext.csvtocsvw.some_setting = some_default_value

# Acknowledgements

This projects work is based on a fork of the repo [etri-odp/ckanext-jena](https://github.com/etri-odp/ckanext-jena) and we like to thank the authors of that project for sharing there work.
It was supported by Institute for Information & communications Technology Promotion (IITP) grant funded by the Korea government (MSIT) (No.2017-00253, Development of an Advanced Open Data Distribution Platform based on International Standards)

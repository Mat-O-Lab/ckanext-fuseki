
# encoding: utf-8

from typing import Any
import ckan.plugins.toolkit as toolkit

import re

def common_member(a, b):
    return any(i in b for i in a)

def fuseki_show_tools(resource):
    from ckanext.fuseki.logic.action import DEFAULT_FORMATS
    format_parts=re.split('/|;', resource['format'].lower().replace(' ',''))
    if common_member(format_parts,DEFAULT_FORMATS):
        return True
    else:
        False

def get_helpers():
    return {
        "fuseki_show_tools": fuseki_show_tools
    }

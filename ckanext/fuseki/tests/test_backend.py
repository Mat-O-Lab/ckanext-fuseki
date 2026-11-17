from unittest import mock

import rdflib
from ckan.plugins import toolkit

from ckanext.fuseki import backend


def _configure(monkeypatch):
    for key, value in {
        "ckanext.fuseki.url": "http://fuseki:3030/",
        "ckanext.fuseki.username": "admin",
        "ckanext.fuseki.password": "secret",
    }.items():
        monkeypatch.setitem(backend.config, key, value)


def test_graph_create_posts_assembly_as_raw_turtle_body(monkeypatch):
    """Fuseki >= 5.5 rejects the multipart upload; the assembly must be sent as
    the raw request body with Content-Type text/turtle."""
    _configure(monkeypatch)
    graph = rdflib.Graph()
    graph.add(
        (
            rdflib.URIRef("urn:test:s"),
            rdflib.URIRef("urn:test:p"),
            rdflib.Literal("ä"),
        )
    )
    monkeypatch.setattr(backend, "create_assembly", lambda *a, **k: graph)
    response = mock.Mock()
    with mock.patch.object(backend.requests, "post", return_value=response) as post:
        backend.graph_create("http://ckan/dataset/x", "ds-id", False, False, "fullOWL", resources=[])

    args, kwargs = post.call_args
    assert args[0] == "http://fuseki:3030/$/datasets"
    assert "files" not in kwargs
    assert kwargs["headers"] == {"Content-Type": "text/turtle"}
    assert isinstance(kwargs["data"], bytes)
    assert "ä".encode("utf-8") in kwargs["data"]
    assert kwargs["auth"] == ("admin", "secret")
    response.raise_for_status.assert_called_once()

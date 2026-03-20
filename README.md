[![Tests](https://github.com/Mat-O-Lab/ckanext-fuseki/actions/workflows/test.yml/badge.svg)](https://github.com/Mat-O-Lab/ckanext-fuseki/actions/workflows/test.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)

# ckanext-fuseki

A CKAN extension for semantic data management in research data portals.
It automatically pushes RDF resources to an Apache Jena Fuseki triple store,
provides a CKAN-authenticated SPARQL proxy that enforces dataset-level access control,
and embeds a YASGUI query interface for interactive SPARQL exploration of linked data.

![Fuseki tab in CKAN dataset view showing access information, SPARQL endpoint, authentication methods, named graphs, and per-resource upload toggles](ckan-fuseki.png)

## Requirements

* **Apache Jena Fuseki** server with custom security configuration (see [Deployment](#deployment) section)
* **CKAN API Token** with admin privileges for background job processing of private datasets

### Fuseki Deployment

This extension requires a **custom Fuseki deployment** with modified security settings to enable CKAN-authenticated access. The necessary files are provided in the `optional/` folder:

- **`optional/fuseki/Dockerfile`** - Custom Fuseki image based on `secoresearch/fuseki:4.9.0`
- **`optional/fuseki/docker-entrypoint.sh`** - Security wrapper that blocks anonymous dataset access
- **`optional/fuseki/index.html`** - Fixed Fuseki UI for subpath deployment
- **`optional/docker-compose.yml`** - Example standalone deployment configuration

See the [optional/README.md](optional/README.md) for standalone deployment instructions, or integrate into your existing Docker Compose setup (see [Deployment](#deployment) section below).

**Optional**: A Sparklis web app for interactive SPARQL querying is also available in the optional folder.

## Features

- **Per-resource upload toggles** — selectively push RDF resources (Turtle, N-Triples, JSON-LD, etc.) to Fuseki
- **Named graphs** — each resource is stored in its own named graph within a dedicated Fuseki dataset
- **CKAN-authenticated SPARQL proxy** — enforces CKAN dataset-level access control on all SPARQL endpoints
  - Public datasets: accessible to anyone via the CKAN proxy
  - Private datasets: require CKAN authentication (browser session or API token)
  - Direct Fuseki access: blocked for anonymous users, admin-only
- **Query Dataset button** — embedded YASGUI interface for interactive SPARQL exploration
- **Persistent & reasoning options** — configurable at dataset level

See [SECURITY.md](SECURITY.md) for the full security architecture.

## Compatibility

| CKAN version    | Compatible? |
| --------------- | ----------- |
| 2.9 and earlier | not tested  |
| 2.10            | ✓ tested    |
| 2.11            | ✓ tested    |


## Installation

### 1. Install the Extension

**From PyPI:**
```bash
pip install ckanext-fuseki
```

**From Source:**
```bash
pip install -e git+https://github.com/Mat-O-Lab/ckanext-fuseki.git#egg=ckanext-fuseki
```

### 2. Deploy Fuseki

Use `secoresearch/fuseki:4.9.0` with the provided configuration files mounted as volumes:

```yaml
services:
  fuseki:
    image: secoresearch/fuseki:4.9.0
    environment:
      - JAVA_OPTIONS=-Xmx10g -Xms10g -DentityExpansionLimit=0
      - ENABLE_DATA_WRITE=true
      - ENABLE_UPDATE=true
      - ENABLE_UPLOAD=true
      - QUERY_TIMEOUT=60000
    volumes:
      - jena_data:/fuseki-base
      - ./path/to/ckanext-fuseki/optional/fuseki/index.html:/jena-fuseki/webapp/index.html
      - ./path/to/ckanext-fuseki/optional/fuseki/shiro.ini:/jena-fuseki/shiro.ini
    networks:
      - your_network
    healthcheck:
      test: ["CMD-SHELL", "wget -qO /dev/null http://localhost:3030/$$/ping || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
```

- **`index.html`** — fixes asset paths for subpath (nginx proxy) deployments
- **`shiro.ini`** — configures HTTP Basic Auth; edit to set the admin password

**Start Fuseki:**
```bash
docker-compose up -d fuseki
```

### 3. Configure CKAN

Add `fuseki` to the `ckan.plugins` setting in your CKAN config file:

```ini
ckan.plugins = ... fuseki
```

### 4. Restart CKAN

```bash
docker-compose restart ckan
# Or for Apache deployment:
sudo service apache2 reload
```

## Config settings

All configuration is read from `ckan.ini` (or the equivalent `CKANINI__` Docker environment variables):

| ckan.ini key | Default | Description |
|---|---|---|
| `ckanext.fuseki.url` | `http://fuseki:3030/` | Direct internal URL of the Fuseki container — **must not** go through nginx |
| `ckanext.fuseki.username` | `admin` | Fuseki admin username — always `admin` (hardcoded by the Fuseki image) |
| `ckanext.fuseki.password` | `admin` | Fuseki admin password — must match the `ADMIN_PASSWORD` env var set on the Fuseki container |
| `ckanext.fuseki.ckan_token` | _(empty)_ | CKAN API token for background job callbacks; required to process private datasets |
| `ckanext.fuseki.formats` | `turtle text/turtle n3 nt hext trig longturtle xml json-ld ld+json jsonld` | Space-separated list of resource formats that trigger upload to the triple store |
| `ckanext.fuseki.ssl_verify` | `true` | Verify SSL certificates when connecting to external resource URLs |
| `ckanext.fuseki.sparklis_url` | _(empty)_ | If set, the query button redirects to this Sparklis instance instead of the built-in SPARQL UI |

Example Docker environment variables (set in `.env`):

```bash
CKANINI__CKANEXT__FUSEKI__URL=http://fuseki:${FUSEKI_PORT}/
CKANINI__CKANEXT__FUSEKI__USERNAME=admin
CKANINI__CKANEXT__FUSEKI__PASSWORD=<your-fuseki-password>
CKANINI__CKANEXT__FUSEKI__CKAN_TOKEN=<your-ckan-api-token>
CKANINI__CKANEXT__FUSEKI__SSL_VERIFY=${SSL_VERIFY}
```

`ckanext.fuseki.url` must be the **container-internal** address (e.g. `http://fuseki:3030/`), not the public nginx URL. CKAN uses this URL for all direct Fuseki API calls and the SPARQL proxy.

If `ckanext.fuseki.ckan_token` is not set, only public resources can be uploaded to the triple store.

## Citation

If you use this software, please cite it. GitHub shows a **"Cite this repository"** button (top right of the repo page) that exports the [CITATION.cff](CITATION.cff) in APA or BibTeX format.

After the first Zenodo release, a DOI-specific BibTeX entry will be available on the Zenodo record. Until then:

```bibtex
@software{hanke_ckanext_fuseki,
  author       = {Hanke, Thomas},
  title        = {ckanext-fuseki},
  url          = {https://github.com/Mat-O-Lab/ckanext-fuseki},
  license      = {AGPL-3.0-or-later},
}
```

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)

## Acknowledgements

This project's work is based on a fork of the repo [etri-odp/ckanext-jena](https://github.com/etri-odp/ckanext-jena), and we like to thank the authors of that project for sharing their work.
It was supported by Institute for Information & communications Technology Promotion (IITP) grant funded by the Korea government (MSIT) (No.2017-00253, Development of an Advanced Open Data Distribution Platform based on International Standards)

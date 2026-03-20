# Optional Fuseki Standalone Setup

This directory contains configuration for running Apache Jena Fuseki as a standalone service for development or testing purposes. The setup mirrors the production deployment in `compose.yaml`.

## Files

- **`fuseki/index.html`** — Custom Fuseki UI with corrected paths for subpath deployment (e.g. behind an nginx `/fuseki/` prefix)
- **`fuseki/shiro.ini`** — Apache Shiro security configuration: controls authentication and endpoint access
- **`docker-compose.yml`** — Standalone deployment using `secoresearch/fuseki:4.9.0`

## Configuration

### Credentials

- **Username**: `admin` — hardcoded by the Fuseki image, always `admin`
- **Password**: set via the `ADMIN_PASSWORD` environment variable in `docker-compose.yml`; overrides whatever is in `shiro.ini` on first container start

**To change the password**, update `ADMIN_PASSWORD` in `docker-compose.yml` and restart the container. Also update `ckanext.fuseki.password` in your CKAN config to match.

### shiro.ini

`fuseki/shiro.ini` is mounted as a volume and controls which endpoints require authentication. It does **not** control the password (that is set by `ADMIN_PASSWORD`). The `shiro.ini` configures:
- Health-check endpoints (`/$/ping`, `/$/status`) as public
- Static UI assets as public
- All admin and data endpoints require HTTP Basic Auth with the `admin` role

JVM and Fuseki behaviour are controlled via environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `JAVA_OPTIONS` | `-Xmx10g -Xms10g -DentityExpansionLimit=0` | JVM heap and entity expansion settings |
| `ENABLE_DATA_WRITE` | `true` | Allow writes via Graph Store Protocol |
| `ENABLE_UPDATE` | `true` | Allow SPARQL UPDATE operations |
| `ENABLE_UPLOAD` | `true` | Allow file uploads |
| `QUERY_TIMEOUT` | `60000` | Maximum query execution time (ms) |

## Usage

### Starting Fuseki

```bash
cd optional
docker-compose up -d
```

### Accessing Fuseki

- **Web UI**: http://localhost:3030/
- **SPARQL Endpoint**: http://localhost:3030/{dataset-uuid}/sparql
- **Sparklis UI**: http://localhost:8080/

### Stopping Fuseki

```bash
cd optional
docker-compose down
```

### Removing All Data

```bash
cd optional
docker-compose down -v
```

## Integration with CKAN

Configure your CKAN instance to connect to Fuseki via `ckan.ini` or the equivalent `CKANINI__` environment variables:

```ini
ckanext.fuseki.url = http://fuseki:3030/
ckanext.fuseki.username = admin
ckanext.fuseki.password = admin
ckanext.fuseki.ckan_token = <your-ckan-api-token>
```

For SPARQL queries via Sparklis, also set:

```ini
ckanext.fuseki.sparklis_url = http://localhost:8080/
```

If CKAN accesses Fuseki through a different internal address than the public URL (e.g. behind nginx), set:

```ini
ckanext.fuseki.internal_url = http://fuseki:3030
```

## Troubleshooting

### Check Fuseki logs
```bash
docker-compose logs -f fuseki
```

### Verify Fuseki is healthy
```bash
curl http://localhost:3030/$$/ping
```

### Check dataset status
```bash
curl -u admin:admin http://localhost:3030/$$/datasets
```

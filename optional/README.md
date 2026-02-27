# Optional Fuseki Standalone Setup

This directory contains configuration for running Apache Jena Fuseki as a standalone service for development or testing purposes.

## What's Changed

The configuration has been modernized to match the production setup:

- ✅ **Updated to secoresearch/fuseki:4.9.0** (modern Fuseki base image)
- ✅ **Environment-based configuration** (replaces manual config.ttl)
- ✅ **Simplified volume mounting** (only /fuseki-base needs to be persisted)
- ✅ **Custom entrypoint** for proper initialization
- ✅ **Fixed index.html** for subpath deployment support
- ✅ **Removed jetty.xml and config.ttl** (now handled by the base image)

## Configuration

The Fuseki service is configured via environment variables in `docker-compose.yml`:

- `JAVA_OPTIONS`: JVM settings (memory: 10GB, entity expansion: unlimited)
- `ADMIN_PASSWORD`: Admin password (default: "admin" - **change in production!**)
- `ENABLE_DATA_WRITE`: Allow write operations via SPARQL Graph Store Protocol
- `ENABLE_UPDATE`: Allow SPARQL UPDATE operations
- `ENABLE_UPLOAD`: Allow file uploads
- `QUERY_TIMEOUT`: Maximum query execution time in milliseconds (60 seconds)

## Usage

### Starting Fuseki

```bash
cd optional
docker-compose up -d
```

### Accessing Fuseki

- **Web UI**: http://localhost:3030/
- **SPARQL Endpoint**: http://localhost:3030/ds/sparql
- **Sparklis UI**: http://localhost:8080/

### Default Credentials

- **Username**: admin
- **Password**: admin

**⚠️ IMPORTANT**: Change the `ADMIN_PASSWORD` in `docker-compose.yml` for production use!

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

## Dataset Configuration

The base image automatically creates a default dataset named "ds" with:
- SPARQL query endpoint
- SPARQL update endpoint
- File upload support
- Graph store protocol support
- SHACL validation endpoint

Additional datasets can be created via the web UI or API.

## Differences from Old Configuration

### Old Setup (stain/jena-fuseki)
- Used manual config.ttl for dataset configuration
- Required custom jetty.xml for server settings
- Complex TDB2 assembly configuration
- Manual inference model setup

### New Setup (secoresearch/fuseki:4.9.0)
- Environment variable-based configuration
- Built-in dataset management
- Simplified deployment
- Better performance and stability
- Easier to maintain and update

## Integration with CKAN

Configure your CKAN instance to connect to Fuseki:

```ini
# In your CKAN config file (e.g., ckan.ini)
ckanext.fuseki.url = http://fuseki:3030
ckanext.fuseki.username = admin
ckanext.fuseki.password = admin
ckanext.fuseki.dataset = ds
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

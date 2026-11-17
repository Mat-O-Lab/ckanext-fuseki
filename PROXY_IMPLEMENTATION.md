# CKAN Fuseki Proxy Implementation

## Overview

This document describes the transparent proxy implementation that secures Fuseki SPARQL endpoints using CKAN API tokens.

## Problem Solved

Previously, Fuseki endpoints were exposed directly through nginx without authentication. The proxy now:
1. Authenticates users via CKAN's permission system (requires `package_show` permission)
2. Forwards requests transparently to Fuseki using admin credentials
3. Returns responses without modification (true transparent forwarding)

## URL Structure

### Proxy Routes (Protected by CKAN Authentication)
- `/dataset/<id>/fuseki/$` - Dataset root page
- `/dataset/<id>/fuseki/$/<path>` - Any Fuseki endpoint (sparql, query, update, data, etc.)

The `$` separator prevents conflicts with existing CKAN routes:
- `/dataset/<id>/fuseki` - Management UI
- `/dataset/<id>/fuseki/status` - Status page
- `/dataset/<id>/fuseki/query` - Redirect to query UI

### Examples
```bash
# SPARQL query endpoint
GET /dataset/iof-mapping/fuseki/$/sparql

# Fuseki query UI
GET /dataset/iof-mapping/fuseki/$/query

# SPARQL update endpoint
POST /dataset/iof-mapping/fuseki/$/update

# Graph Store Protocol
GET /dataset/iof-mapping/fuseki/$/data?graph=http://example.org/graph
```

## How It Works

### 1. Request Flow
```
User Request → Nginx → CKAN → Proxy View → Fuseki (internal network)
                ↓
         CKAN Auth Check
```

### 2. UUID Resolution
The proxy accepts both dataset names and UUIDs, but Fuseki datasets are identified by UUIDs:
```python
# User can use name: /dataset/iof-mapping/fuseki/$/sparql
# Proxy resolves to UUID: http://fuseki:3030/2f159c41-.../sparql
pkg_dict = toolkit.get_action('package_show')({'user': user}, {'id': id})
dataset_uuid = pkg_dict['id']  # Always UUID
```

### 3. Which Fuseki URL is used

The proxy (and all other calls from CKAN to Fuseki) builds its target from `ckanext.fuseki.url`:
```ini
# Recommended: direct container address
ckanext.fuseki.url = http://fuseki:3030/
```
`ckanext.fuseki.internal_url` is optional and used **only** for the availability (ping) check; it does not affect the proxy.

A public URL such as `https://your-host/fuseki/` also works if the reverse proxy forwards `/fuseki/` to Fuseki (not to CKAN) and passes the admin login, but every call then makes an extra hop through the reverse proxy. There is no automatic detection or rewriting of the URL.

### 4. Transparent Forwarding

The proxy forwards requests without modification:

```python
# Forward ALL headers (except Host)
headers = dict(request.headers)
headers.pop('Host', None)

# Forward request with stream=True to avoid buffering
response = requests.request(
    method=request.method,
    url=target_url,
    headers=headers,
    data=request.get_data(),
    auth=(username, password),
    stream=True,
    verify=SSL_VERIFY,
    allow_redirects=False,
    timeout=300
)

# Return raw response without decoding
def generate():
    for chunk in response.raw.stream(8192, decode_content=False):
        yield chunk

return Response(
    generate(),
    status=response.status_code,
    headers=dict(response.raw.headers)  # ALL headers unchanged
)
```

### 5. Security Model

#### CKAN Side
- User must have `package_show` permission on the dataset
- Checks performed via `toolkit.get_action('package_show')`
- Returns 403 if unauthorized, 404 if not found

#### Fuseki Side
- Proxy authenticates with admin credentials
- Fuseki's shiro.ini blocks anonymous access: `/** = authcBasic,user[admin]` (see `optional/fuseki/shiro.ini`). The stock Fuseki image allows anonymous queries, so the provided shiro.ini must be active
- Only proxy can access Fuseki (not direct browser access)

## Testing

### Test Proxy with curl

```bash
# Test without authentication (should return 403)
curl -k 'https://docker-dev.iwm.fraunhofer.de/dataset/iof-mapping/fuseki/$/sparql'

# Test with CKAN session cookie (should work if user has permission)
curl -k -b cookies.txt 'https://docker-dev.iwm.fraunhofer.de/dataset/iof-mapping/fuseki/$/sparql' \
  -H 'Accept: application/sparql-results+json' \
  -d 'query=SELECT * WHERE { ?s ?p ?o } LIMIT 5'

# Test direct Fuseki access (should be blocked by shiro)
curl 'http://fuseki:3030/2f159c41-c630-4e9b-bfa6-4df7dfdf0198/sparql'
```

### Verify in Logs

```bash
# Check CKAN logs for proxy activity
docker logs pmd-ckan-ckan-1 --tail 50 | grep fuseki

# Expected output:
# INFO  [ckanext.fuseki.views] Proxying request to Fuseki: GET http://fuseki:3030/UUID/sparql
# INFO  [ckanext.fuseki.views] Fuseki response: 200
```

## Troubleshooting

### 404 Errors
- **Proxy returns 404**: Dataset exists in CKAN but not uploaded to Fuseki yet
- **Solution**: Upload dataset to Fuseki via `/dataset/<id>/fuseki` management UI

### 403 Errors
- **User not logged in**: Requires CKAN authentication
- **User lacks permission**: Must have `package_show` permission on dataset
- **Solution**: Log in or check dataset permissions

### 502 Bad Gateway
- **Fuseki not running**: Check `docker ps | grep fuseki`
- **Wrong URL**: Verify `ckanext.fuseki.url` (with trailing slash)
- **Solution**: Restart Fuseki or fix configuration

### Very fast 404 responses (< 30ms)
- **Cause**: `ckanext.fuseki.url` points at a CKAN/nginx route that ends up back in CKAN instead of at Fuseki
- **Solution**: Point it at Fuseki (`http://fuseki:3030/`) or make sure the reverse proxy routes `/fuseki/` to the Fuseki container

## Implementation Files

- `ckanext/fuseki/views.py` - Proxy implementation
- `ckanext/fuseki/logic/auth.py` - Authorization (delegates to `package_show`)
- `ckanext/fuseki/helpers.py` - Helper functions (fuseki_sparql_url)
- `optional/fuseki/shiro.ini` - Fuseki security configuration (anonymous access blocked)
- `optional/fuseki/docker-entrypoint.sh` - installs it on every Fuseki start

## Configuration Example

```ini
# CKAN Configuration (ckan.ini)
ckanext.fuseki.url = http://fuseki:3030/
ckanext.fuseki.internal_url =   # optional, only for the availability check
ckanext.fuseki.username = admin
ckanext.fuseki.password = your-secure-password
```

```ini
# Fuseki Shiro Configuration (shiro.ini)
[urls]
/** = authcBasic,user[admin]  # Block anonymous access to ALL endpoints
```

## Notes

- The proxy handles ALL HTTP methods: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
- Query parameters are preserved and forwarded unchanged
- Request/response bodies are streamed without buffering
- All headers except `Host` are forwarded transparently
- The proxy works with both dataset names and UUIDs
- Fuseki datasets are always created with UUIDs, not names

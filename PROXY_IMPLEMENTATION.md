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

### 3. Internal vs External URLs

**CRITICAL FIX**: The proxy must use internal docker network addresses, not external nginx URLs.

#### Configuration
```ini
# External URL (used by browser/external access)
ckanext.fuseki.url = https://docker-dev.iwm.fraunhofer.de/fuseki

# Internal URL (used by proxy to avoid nginx loop)
ckanext.fuseki.internal_url = http://fuseki:3030
```

#### Auto-Detection
If `ckanext.fuseki.internal_url` is not set, the proxy automatically detects nginx loops:
```python
if '/fuseki/' in fuseki_external_url:
    fuseki_internal_url = 'http://fuseki:3030'
    log.warning("Using internal Fuseki URL to avoid nginx loop")
```

**Why This Matters**: 
- Using external URL creates a loop: CKAN → Nginx → CKAN → Nginx → ...
- Using internal URL goes directly: CKAN → Fuseki (Docker network)

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
- Fuseki's shiro.ini blocks anonymous access: `/** = authc, roles[admin]`
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
# WARNI [ckanext.fuseki.views] Using internal Fuseki URL http://fuseki:3030 instead of external...
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
- **Wrong internal URL**: Verify `ckanext.fuseki.internal_url` or auto-detection
- **Solution**: Restart Fuseki or fix configuration

### Nginx Loop (Fast 404 responses)
- **Symptom**: Very fast 404 responses (< 30ms), check logs for "render time 0.026 seconds"
- **Cause**: Using external URL instead of internal, creating nginx loop
- **Solution**: Already fixed - proxy auto-detects and uses `http://fuseki:3030`

## Implementation Files

- `ckanext/fuseki/views.py` - Proxy implementation
- `ckanext/fuseki/logic/auth.py` - Authorization (delegates to `package_show`)
- `ckanext/fuseki/helpers.py` - Helper functions (fuseki_sparql_url)
- `config/fuseki/docker-entrypoint.sh` - Fuseki security configuration

## Configuration Example

```ini
# CKAN Configuration (ckan.ini)
ckanext.fuseki.url = https://docker-dev.iwm.fraunhofer.de/fuseki
ckanext.fuseki.internal_url = http://fuseki:3030  # Optional, auto-detected
ckanext.fuseki.username = admin
ckanext.fuseki.password = your-secure-password
```

```ini
# Fuseki Shiro Configuration (shiro.ini)
[urls]
/** = authc, roles[admin]  # Block anonymous access to ALL endpoints
```

## Notes

- The proxy handles ALL HTTP methods: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
- Query parameters are preserved and forwarded unchanged
- Request/response bodies are streamed without buffering
- All headers except `Host` are forwarded transparently
- The proxy works with both dataset names and UUIDs
- Fuseki datasets are always created with UUIDs, not names

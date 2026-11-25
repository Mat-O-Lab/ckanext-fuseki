# Fuseki Security with CKAN Authentication

## Overview

This extension now provides secure access to Fuseki SPARQL endpoints through CKAN authentication. Instead of allowing anonymous access to Fuseki datasets, all access is proxied through CKAN, which checks permissions based on dataset visibility.

## Architecture

### Security Flow

```
User Request → CKAN Proxy (/dataset/{id}/fuseki/$/*) 
              ↓ Checks CKAN permissions
              ↓ Authenticates with Fuseki admin credentials
              → Fuseki Dataset ({fuseki-url}/{id}/*)
              → Returns data to user

Direct Access → Fuseki ({fuseki-url}/{id}/*) 
               ✗ BLOCKED (requires admin authentication)
```

**Notes:** 
- The `$` separator in the URL prevents route conflicts with existing CKAN routes like `/dataset/{id}/fuseki` (management UI) and `/dataset/{id}/fuseki/status`.
- The proxy automatically resolves dataset names/slugs to UUIDs, since Fuseki datasets are created using UUIDs. Both `/dataset/my-dataset-name/fuseki/$/sparql` and `/dataset/abc-123-uuid/fuseki/$/sparql` will work correctly.

### Components

1. **Fuseki Security Configuration** (`optional/fuseki/shiro.ini`)
   - Uses a `shiro.ini` that requires the Fuseki admin login for all dataset endpoints (anonymous access is blocked)
   - Requires authentication for all dataset endpoints: `/** = authcBasic,user[admin]`

2. **CKAN Transparent Proxy** (`ckanext/fuseki/views.py`)
   - Route: `/dataset/<id>/fuseki/$/<path:service_path>`
   - The `$` separator prevents conflicts with existing CKAN UI routes
   - Accepts all HTTP methods (GET, POST, PUT, DELETE, etc.); write operations require `package_update`, reads require `package_show`
   - Resolves dataset name/slug to UUID (Fuseki uses UUIDs)
   - Checks CKAN `package_show` permission
   - Forwards requests to Fuseki with admin credentials

3. **Authorization** (`ckanext/fuseki/logic/auth.py`)
   - `fuseki_proxy` auth function
   - Allows anonymous access for public datasets
   - Requires authentication for private datasets

4. **Helper Updates** (`ckanext/fuseki/helpers.py`)
   - `fuseki_sparql_url()` now returns CKAN proxy URL
   - All generated links use the secure proxy

## Access Control

### Public Datasets
- ✅ Anonymous users can access SPARQL endpoints
- ✅ No CKAN API token required
- ℹ️ CKAN checks dataset is public before forwarding

### Private Datasets
- ✅ Dataset owner/members can access
- ✅ Requires CKAN authentication (API token or session)
- ✗ Unauthorized users receive 403 Forbidden
- ℹ️ Request never reaches Fuseki if unauthorized

### Direct Fuseki Access
- ✅ Admin users can access Fuseki UI directly
- ✅ Fuseki admin interface: `/fuseki/#/manage`
- ✗ Direct dataset access blocked for non-admins
- ⚠️ The Fuseki `admin` login bypasses every CKAN check (private datasets, read/write split, CSRF). If Fuseki is published (e.g. an nginx `/fuseki/` route) use a strong `ckanext.fuseki.password` (it is also rendered into `shiro.ini` via `ADMIN_PASSWORD`), or do not publish the route and use the container-internal `ckanext.fuseki.url` so Fuseki is reachable only through the CKAN proxy.

### Proxy permissions per service

| Service | Method | Required |
|---|---|---|
| `sparql`, `query`, `get` | any | read (`package_show`) |
| `data` | GET/HEAD/OPTIONS | read |
| `data` | PUT/POST/DELETE/PATCH | `package_update` |
| `update`, `upload` | any | `package_update` |
| anything else | any | `package_update` |

Allowlist: only the known read requests pass with read access. Paths with `.`/`..` segments are rejected (400).

CSRF: CKAN (2.10+) rejects cookie-session POST/PUT/PATCH/DELETE without a CSRF token. The proxy view is exempt so Sparklis/YASGUI query POSTs work, and the proxy checks CSRF itself for write requests. Requests authenticated with an API token (`Authorization` header) skip CSRF, as everywhere in CKAN.

Direct writes (`update`, `upload`, `data`) are not tracked by CKAN; the next Create/Update rebuilds the dataset from the CKAN resources and discards them.

## Deployment

### Required Files

This extension requires a custom Fuseki deployment with modified security settings. The necessary files are provided in the `optional/` folder:

1. **`optional/fuseki/Dockerfile`** - Builds on `secoresearch/fuseki:6.2.0` and bakes in the `shiro.ini` and the entrypoint wrapper
2. **`optional/fuseki/docker-entrypoint.sh`** - Entrypoint wrapper: copies the restrictive `shiro.ini` to `/fuseki-base/shiro.ini` on every start (and refuses to start without it), then starts Fuseki
3. **`optional/fuseki/shiro.ini`** - Requires the Fuseki `admin` login for everything except the health endpoints. **This is what blocks anonymous access.** The stock `secoresearch/fuseki` image allows anonymous SPARQL queries (`/** = anon`) and only copies its `shiro.ini` to the volume on the first start, so running the stock image without this file leaves all datasets public.
4. **`optional/docker-compose.yml`** - Example deployment configuration

### 1. Fuseki Container Setup

**Option A: Mount Entrypoint (Simpler - No Build Required)**

Mount the wrapper script as the entrypoint **and** the `shiro.ini` it installs:

```yaml
fuseki:
  image: secoresearch/fuseki:6.2.0
  entrypoint: /custom-entrypoint.sh
  environment:
    - ADMIN_PASSWORD=${FUSEKI_PASSWORD}
    - JDK_JAVA_OPTIONS=-Xmx10g -Xms10g -DentityExpansionLimit=0 -Dfuseki:allowAddByConfigFile=true
  volumes:
    - ./ckan_plugins/ckanext-fuseki/optional/fuseki/docker-entrypoint.sh:/custom-entrypoint.sh:ro
    - ./ckan_plugins/ckanext-fuseki/optional/fuseki/shiro.ini:/fuseki-init/shiro.ini:ro
    - jena_data:/fuseki-base
```

**Deploy**
```bash
docker-compose up -d fuseki
```

**Option B: Build Custom Image**

Build the custom image (wrapper and `shiro.ini` are baked in):

```yaml
fuseki:
  build:
    context: ckan_plugins/ckanext-fuseki/optional/fuseki/
  environment:
    - ADMIN_PASSWORD=${FUSEKI_PASSWORD}
    - JDK_JAVA_OPTIONS=-Xmx10g -Xms10g -DentityExpansionLimit=0 -Dfuseki:allowAddByConfigFile=true
  volumes:
    - jena_data:/fuseki-base
```

**Build and Deploy**
```bash
docker-compose build fuseki
docker-compose up -d fuseki
```

### 2. Restart CKAN

For the new proxy route to be available:

```bash
docker-compose restart ckan
```

### 3. Verify Fuseki Security

Test that anonymous access to datasets is blocked:

```bash
# This must return 401 Unauthorized. If it returns 200, the restrictive shiro.ini is not active
# (the stock image allows anonymous queries) - the datasets are public.
curl http://fuseki:3030/{dataset-id}/sparql?query=SELECT%20*%20WHERE%20{?s%20?p%20?o}%20LIMIT%2010

# Admin access should work
curl -u admin:password http://fuseki:3030/{dataset-id}/sparql?query=SELECT%20*%20WHERE%20{?s%20?p%20?o}%20LIMIT%2010
```

### 4. Verify CKAN Proxy

Test the CKAN proxy with a public dataset:

```bash
# Public dataset - no auth required
curl 'https://your-ckan-site.com/dataset/{public-dataset-id}/fuseki/$/sparql?query=SELECT%20*%20WHERE%20{?s%20?p%20?o}%20LIMIT%2010'

# Private dataset - requires API token
curl -H "Authorization: YOUR_API_TOKEN" \
  'https://your-ckan-site.com/dataset/{private-dataset-id}/fuseki/$/sparql?query=SELECT%20*%20WHERE%20{?s%20?p%20?o}%20LIMIT%2010'
```

## Reverse Proxy Configuration

Fuseki is normally forwarded under `/fuseki/` (this is what the pmd-ckan stack does in `config/nginx/default.conf.template`). Anonymous access is blocked by Fuseki itself (`shiro.ini`), not by nginx:

```nginx
location /fuseki/ {
    proxy_pass http://fuseki:3030/;     # the trailing slash strips the /fuseki/ prefix
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_buffering off;
}
```

**Optional hardening.** To additionally keep the dataset endpoints (`/fuseki/<uuid>/...`) away from the internet, allow them only from the Docker network. Regex locations take precedence over the prefix location above; the regex must be quoted because of the `{36}`, and `proxy_pass` needs the `rewrite` because regex locations cannot carry a URI:

```nginx
location ~ "^/fuseki/[a-f0-9-]{36}(/|$)" {
    allow 172.16.0.0/12;                 # Docker network (CKAN reaches Fuseki from here)
    deny all;
    rewrite ^/fuseki/(.*)$ /$1 break;
    proxy_pass http://fuseki:3030;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_buffering off;
}
```

Tested with nginx 1.30 and Fuseki 6.2.0: from inside the allowed range anonymous dataset queries return 401 (Shiro) and admin queries 200; from outside the range dataset endpoints return 403 even with the admin login, while `/fuseki/$/ping` and the admin API (with login) stay reachable. Adjust the `allow` range to your network. If your nginx sees all clients with a Docker gateway address (e.g. requests arrive through a local proxy), the `allow` rule cannot tell them apart; then rely on Shiro.

## API Endpoints

All endpoints use the `/dataset/{id}/fuseki/$/` prefix to avoid conflicts with CKAN UI routes.

### SPARQL Query
```
GET/POST /dataset/{id}/fuseki/$/sparql
```

### SPARQL Update
```
POST /dataset/{id}/fuseki/$/update
```

### Graph Store Protocol
```
GET/PUT/POST/DELETE /dataset/{id}/fuseki/$/data?graph=<graph-uri>
```

### File Upload
```
POST /dataset/{id}/fuseki/$/upload
```

All endpoints support the same parameters and content types as Fuseki's native endpoints.

**Example URLs:**
- Query: `https://your-ckan.org/dataset/abc-123/fuseki/$/sparql?query=SELECT...`
- Update: `https://your-ckan.org/dataset/abc-123/fuseki/$/update`
- Data: `https://your-ckan.org/dataset/abc-123/fuseki/$/data?graph=http://example.org/graph`

## Configuration

Required CKAN configuration (already in place):

```ini
ckanext.fuseki.url = http://fuseki:3030/
ckanext.fuseki.username = admin
ckanext.fuseki.password = <admin-password>
```

Keep the trailing slash in the URL: some calls append `$/datasets` directly. Or via environment variables:

```bash
CKANINI__CKANEXT__FUSEKI__URL=http://fuseki:3030/
CKANINI__CKANEXT__FUSEKI__USERNAME=admin
CKANINI__CKANEXT__FUSEKI__PASSWORD=<admin-password>
```

## Authentication Methods

### API Token (Recommended for Programmatic Access)

```bash
curl -H "Authorization: YOUR_API_TOKEN" \
  'https://ckan-site.com/dataset/{id}/fuseki/$/sparql?query=...'
```

### Session Cookie (For Browser Access)

When logged into CKAN, the browser session cookie is used automatically.

## Troubleshooting

### 401 Unauthorized from Fuseki
- ✅ Expected behavior - anonymous access is blocked
- ✅ Use CKAN proxy instead: `/dataset/{id}/fuseki/$/sparql`

### 403 Forbidden from CKAN Proxy
- Check dataset visibility
- Check user permissions
- Verify API token is valid

### 502 Bad Gateway
- Fuseki service may be down
- Check Fuseki is running: `docker-compose ps fuseki`
- Check Fuseki logs: `docker-compose logs fuseki`

### Anonymous queries return 200 (datasets are public)
- The restrictive `shiro.ini` is not active, e.g. the stock image or the wrong entrypoint is used
- Rebuild the image: `docker-compose build fuseki`
- Check the installed file: `docker-compose exec fuseki grep -n '^/' /fuseki-base/shiro.ini` (must end with `/** = authcBasic,user[admin]`)
- The wrapper aborts with `ERROR: /fuseki-init/shiro.ini missing` if the file is absent

## Security Benefits

✅ **Centralized Authentication** - All access controlled by CKAN  
✅ **Dataset-Level Permissions** - Respects CKAN visibility settings  
✅ **No Credential Exposure** - Users never need Fuseki admin password  
✅ **Audit Trail** - All access logged through CKAN  
✅ **Standard SPARQL** - Works with any SPARQL client  
✅ **Transparent Proxy** - All Fuseki services available  

## Migration Notes

### Existing Dataset Links

The SPARQL resource links created in datasets will automatically use the new proxy URL after CKAN restart. Existing links in external applications should be updated to use:

```
https://your-ckan-site.com/dataset/{dataset-id}/fuseki/$/sparql
```

Instead of:

```
http://fuseki:3030/{dataset-id}/sparql
```

**Note:** The `$` character in URLs should be properly escaped in shell commands and may need URL encoding (`%24`) in some contexts.

### Backward Compatibility

Direct Fuseki URLs will still work for admin users with proper credentials, but public/unauthenticated access will be blocked.

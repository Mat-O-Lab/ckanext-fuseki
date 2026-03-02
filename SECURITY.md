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

1. **Fuseki Security Configuration** (`config/fuseki/docker-entrypoint.sh`)
   - Modifies `shiro.ini` on startup to block anonymous dataset access
   - Requires authentication for all dataset endpoints: `/** = authc, roles[admin]`

2. **CKAN Transparent Proxy** (`ckanext/fuseki/views.py`)
   - Route: `/dataset/<id>/fuseki/$/<path:service_path>`
   - The `$` separator prevents conflicts with existing CKAN UI routes
   - Accepts all HTTP methods (GET, POST, PUT, DELETE, etc.)
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
- ℹ️ Only admin credentials work

## Deployment

### Required Files

This extension requires a custom Fuseki deployment with modified security settings. The necessary files are provided in the `optional/` folder:

1. **`optional/fuseki/Dockerfile`** - Builds on `secoresearch/fuseki:4.9.0` base image
2. **`optional/fuseki/docker-entrypoint.sh`** - Custom entrypoint that modifies `shiro.ini` to block anonymous access
3. **`optional/fuseki/index.html`** - Fixed Fuseki UI for subpath deployment
4. **`optional/docker-compose.yml`** - Example deployment configuration

### 1. Fuseki Container Setup

**Option A: Mount Entrypoint (Simpler - No Build Required)**

Just mount the security wrapper script as the entrypoint:

```yaml
fuseki:
  image: secoresearch/fuseki:4.9.0
  entrypoint: /custom-entrypoint.sh
  environment:
    - ADMIN_PASSWORD=${FUSEKI_PASSWORD}
    - JAVA_OPTIONS=-Xmx10g -Xms10g -DentityExpansionLimit=0
  volumes:
    - ./config/fuseki/docker-entrypoint.sh:/custom-entrypoint.sh:ro
    - jena_data:/fuseki-base
```

**Deploy**
```bash
docker-compose up -d fuseki
```

**Option B: Build Custom Image (includes fixed index.html)**

Build a custom image with the security wrapper:

```yaml
fuseki:
  build:
    context: ckan_plugins/ckanext-fuseki/optional/fuseki/
  environment:
    - ADMIN_PASSWORD=${FUSEKI_PASSWORD}
    - JAVA_OPTIONS=-Xmx10g -Xms10g -DentityExpansionLimit=0
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
# This should return 401 Unauthorized
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

## Reverse Proxy Configuration (Optional)

If you want to completely block direct Fuseki access from the internet, configure your reverse proxy (Nginx):

```nginx
# Block direct dataset access from external clients
location ~ ^/fuseki/[a-f0-9-]{36} {
    # Only allow from internal network or reject
    allow 172.16.0.0/12;  # Docker network
    deny all;
}

# Allow Fuseki admin interface for admins
location ~ ^/fuseki/(#|\$) {
    proxy_pass http://fuseki:3030;
    # Optional: restrict to admin IPs
}

# Allow CKAN proxy (handles its own auth)
location /dataset/ {
    proxy_pass http://ckan:5000;
}
```

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
ckanext.fuseki.url = http://fuseki:3030
ckanext.fuseki.username = admin
ckanext.fuseki.password = <admin-password>
```

Or via environment variables:

```bash
CKANINI__CKANEXT__FUSEKI__URL=http://fuseki:3030
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
- ✅ Use CKAN proxy instead: `/dataset/{id}/fuseki/sparql`

### 403 Forbidden from CKAN Proxy
- Check dataset visibility
- Check user permissions
- Verify API token is valid

### 502 Bad Gateway
- Fuseki service may be down
- Check Fuseki is running: `docker-compose ps fuseki`
- Check Fuseki logs: `docker-compose logs fuseki`

### shiro.ini not modified
- Check docker-entrypoint.sh has execute permissions
- Rebuild Fuseki image: `docker-compose build fuseki`
- Check logs: `docker-compose logs fuseki | grep "CKAN Security"`

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

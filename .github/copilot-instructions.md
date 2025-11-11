# Kubernetes Ingress Dashboard - AI Agent Instructions

## Project Overview
Real-time Flask + SocketIO web dashboard for visualizing Kubernetes Ingress resources across clusters. Single-file architecture (`app.py`) with WebSocket updates and YAML inspection capabilities.

## Architecture & Key Components

### Core Application Pattern (`app.py`)
- **Factory pattern**: `create_app(test_config=None)` returns `(app, socketio)` tuple
- **Dual-mode operation**: In-cluster K8s config OR local kubeconfig (checked via `KUBECONFIG` env var)
- **Mock fallback**: `generate_mock_ingresses()` provides test data when K8s unavailable
- **Background updates**: 30-second polling thread broadcasts via SocketIO (disabled in tests)
- **Global caching**: `INGRESS_CACHE` dict with threading lock (currently unused but available)

### Kubernetes Integration
```python
# Config loading hierarchy (app.py:16-46)
1. load_incluster_config()  # ServiceAccount token + mounted certs
2. KUBECONFIG env var
3. ~/.kube/config
4. ~/kube/config (fallback)
```

**RBAC requirements**: Read-only access to `networking.k8s.io/ingresses` (see `k8s-deployment.yaml`)

### Testing Pattern
Tests inject `test_config={'mock_resources': [...]}` to override `get_ingress_resources()` globally. The factory cleans up via `@app.teardown_appcontext` restoring original function.

## Development Workflows

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run with hot reload (requires kubeconfig)
python app.py  # Starts on port 5000 with debug=True

# Alternative: Gunicorn with SocketIO
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 wsgi:app
```

**Critical**: Use `eventlet` worker class for SocketIO support. Standard workers will break WebSocket connections.

### Testing
```bash
pytest  # Auto-discovers tests/ via pyproject.toml
```

Tests use Flask test client with `TESTING=True` flag. SocketIO clients are NOT tested (only HTTP routes).

### Deployment Modes

**Docker (multi-stage build)**:
```bash
docker build -t ingress-dashboard:latest .
docker run -p 5000:5000 ingress-dashboard
```
- Stage 1: Builds dependencies in venv (`/opt/venv`)
- Stage 2: Copies venv to slim image, runs as non-root user (UID 1001)
- CMD: `gunicorn --worker-class eventlet -w 1`

**Kubernetes**:
```bash
kubectl apply -f k8s-deployment.yaml
```
- Uses ServiceAccount `ingress-dashboard-sa` with ClusterRole for ingress read access
- Health probe on `/health` endpoint
- ClusterIP Service exposing port 80 → 5000

## Code Conventions

### Filtering Pattern
All filters use **case-insensitive string matching**:
```python
# In get_ingress_resources() and SocketIO handlers
filtered = [r for r in resources 
            if str(r.get(key, '')).lower() == str(value).lower()]
```

### Error Handling
- All K8s operations wrapped in try/except returning mock data on failure
- Extensive logging at INFO level: `logger.info(f"Filtered ingresses: {len(...)}")`
- Traceback printed to console via `traceback.print_exc()`

### YAML Conversion (`convert_ingress_to_yaml`)
Manually constructs clean dict from K8s object (avoids `client.ApiClient().sanitize_for_serialization()`). Conditionally includes labels/annotations to reduce noise.

## Frontend Integration

### SocketIO Events
- **Server → Client**: `'ingress_update'` with array of ingress dicts
- **Client → Server**: 
  - `'connect'` → immediate data push
  - `'get_ingresses'` (filters: dict) → filtered data push

### REST Endpoints
- `GET /` → Main dashboard (`templates/index.html`)
- `GET /health` → JSON health check with K8s availability status
- `GET /ingress/yaml/<namespace>/<name>` → Returns YAML for specific ingress

## Dependencies & Configuration

**Package management**: Dual system (Poetry in `pyproject.toml` + pip in `requirements.txt`)

**Key dependencies**:
- `flask-socketio` + `eventlet` (async_mode='threading' in app.py)
- `kubernetes` Python client v24+
- `PyYAML` for YAML serialization

**Gunicorn config** (`gunicorn_config.py`): 2 sync workers for non-SocketIO mode. Override with `--worker-class eventlet` for SocketIO.

## Common Tasks

**Add new filter field**: Update `ingress_details` dict in `get_ingress_resources()`, then use existing filtering loop (no changes needed).

**Change update frequency**: Modify `time.sleep(30)` in `background_update()` thread.

**Add new K8s resource**: Create parallel function to `get_ingress_resources()` using appropriate API client (e.g., `client.CoreV1Api()` for Services).

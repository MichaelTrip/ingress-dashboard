import logging
import os
import threading
import time
import traceback
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Version information from environment variables
APP_VERSION = os.getenv('APP_VERSION', 'dev')
BUILD_DATE = os.getenv('BUILD_DATE', 'unknown')
GIT_COMMIT = os.getenv('GIT_COMMIT', 'unknown')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log version information on startup
logger.info(f"Starting Kubernetes Ingress Dashboard")
logger.info(f"Version: {APP_VERSION}")
logger.info(f"Build Date: {BUILD_DATE}")
logger.info(f"Git Commit: {GIT_COMMIT}")


def get_refresh_interval_seconds():
    """Get background refresh interval from env with validation."""
    refresh_interval_raw = os.getenv('REFRESH_INTERVAL_SECONDS', '30')

    try:
        refresh_interval = int(refresh_interval_raw)
    except ValueError:
        logger.warning(
            "Invalid REFRESH_INTERVAL_SECONDS='%s'. Falling back to 30 seconds.",
            refresh_interval_raw
        )
        return 30

    if refresh_interval < 5:
        logger.warning(
            "REFRESH_INTERVAL_SECONDS=%s is too low. Using minimum of 5 seconds.",
            refresh_interval
        )
        return 5

    return refresh_interval

# Global cache to improve performance
INGRESS_CACHE = {
    'resources': [],
    'last_updated': 0,
    'lock': threading.Lock()
}

def load_kubernetes_config():
    """
    Attempt to load Kubernetes configuration
    """
    try:
        # First, try in-cluster configuration
        config.load_incluster_config()
        logger.info("Using in-cluster Kubernetes configuration")
        return True
    except config.ConfigException:
        # Try local kubeconfig
        try:
            # Check for custom kubeconfig path
            custom_kubeconfig = os.getenv('KUBECONFIG')

            if custom_kubeconfig and os.path.exists(custom_kubeconfig):
                logger.info(f"Using custom kubeconfig: {custom_kubeconfig}")
                config.load_kube_config(custom_kubeconfig)
                return True

            # Try default kubeconfig locations
            default_locations = [
                os.path.expanduser('~/.kube/config'),
                os.path.expanduser('~/kube/config')
            ]

            for kubeconfig_path in default_locations:
                if os.path.exists(kubeconfig_path):
                    logger.info(f"Using kubeconfig: {kubeconfig_path}")
                    config.load_kube_config(kubeconfig_path)
                    return True

            logger.warning("No valid kubeconfig found")
            return False

        except Exception as e:
            logger.error(f"Error loading kubeconfig: {e}")
            return False

def generate_mock_ingresses():
    """
    Generate mock Ingress resources for testing
    """
    return [
        {
            'name': 'example-ingress-1',
            'namespace': 'default',
            'hostname': 'app1.example.com',
            'ingress_class': 'nginx',
            'status': 'Active',
            'creation_timestamp': str(time.time())
        },
        {
            'name': 'example-ingress-2',
            'namespace': 'kube-system',
            'hostname': 'app2.example.com',
            'ingress_class': 'traefik',
            'status': 'Pending',
            'creation_timestamp': str(time.time())
        }
    ]


def generate_mock_httproutes():
    return [
        {
            'name': 'example-httproute-1',
            'namespace': 'default',
            'hostnames': 'app1.example.com',
            'parent_ref': 'example-gateway',
            'status': 'Active',
            'creation_timestamp': str(time.time())
        }
    ]


def generate_mock_gateways():
    return [
        {
            'name': 'example-gateway',
            'namespace': 'default',
            'gateway_class': 'example-gatewayclass',
            'listeners': 'http:80',
            'status': 'Active',
            'creation_timestamp': str(time.time())
        }
    ]


def generate_mock_gatewayclasses():
    return [
        {
            'name': 'example-gatewayclass',
            'namespace': 'cluster-wide',
            'controller': 'example.io/gateway-controller',
            'description': 'Example GatewayClass',
            'status': 'Active',
            'creation_timestamp': str(time.time())
        }
    ]

def _list_gateway_api_resources(custom_api, plural, namespaced=True):
    versions_to_try = ['v1', 'v1beta1', 'v1alpha2']
    last_error = None

    for version in versions_to_try:
        try:
            data = custom_api.list_cluster_custom_object(
                group='gateway.networking.k8s.io',
                version=version,
                plural=plural
            )
            return data, version
        except ApiException as e:
            last_error = e
            if e.status == 403 and namespaced:
                try:
                    core_v1 = client.CoreV1Api()
                    namespaces = core_v1.list_namespace().items
                    items = []
                    for ns in namespaces:
                        ns_name = ns.metadata.name
                        try:
                            ns_data = custom_api.list_namespaced_custom_object(
                                group='gateway.networking.k8s.io',
                                version=version,
                                namespace=ns_name,
                                plural=plural
                            )
                            items.extend(ns_data.get('items', []))
                        except ApiException:
                            continue
                    return {'items': items}, version
                except Exception as ns_error:
                    logger.warning("Gateway API namespaced fallback failed for %s/%s: %s", version, plural, ns_error)
            elif e.status != 404:
                logger.warning("Gateway API list failed for %s/%s: %s", version, plural, e)
        except Exception as e:
            last_error = e
            logger.warning("Gateway API list failed for %s/%s: %s", version, plural, e)

    if last_error:
        raise last_error

    return {'items': []}, None


def _get_gateway_api_resource(custom_api, plural, name, namespace=None):
    versions_to_try = ['v1', 'v1beta1', 'v1alpha2']
    last_error = None

    for version in versions_to_try:
        try:
            if namespace:
                data = custom_api.get_namespaced_custom_object(
                    group='gateway.networking.k8s.io',
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name
                )
            else:
                data = custom_api.get_cluster_custom_object(
                    group='gateway.networking.k8s.io',
                    version=version,
                    plural=plural,
                    name=name
                )
            return data
        except ApiException as e:
            last_error = e
            if e.status != 404:
                logger.warning("Gateway API get failed for %s/%s %s: %s", version, plural, name, e)
        except Exception as e:
            last_error = e
            logger.warning("Gateway API get failed for %s/%s %s: %s", version, plural, name, e)

    if last_error:
        raise last_error

    return {}


def get_ingress_resources(filters=None, force_refresh=False):
    """
    Retrieve and filter Ingress resources
    """
    try:
        if not load_kubernetes_config():
            logger.warning("Cannot load Kubernetes configuration")
            return generate_mock_ingresses()

        filters = filters or {}
        logger.info(f"Received filters: {filters}")

        networking_v1 = client.NetworkingV1Api()
        ingresses = networking_v1.list_ingress_for_all_namespaces()

        ingress_list = []
        for ing in ingresses.items:
            hostname = (
                ing.spec.rules[0].host
                if ing.spec.rules and ing.spec.rules[0].host
                else 'N/A'
            )

            ingress_class = (
                ing.spec.ingress_class_name or
                (getattr(ing.spec, 'backend', None).resource.kind
                 if getattr(ing.spec, 'backend', None) else 'Default')
            )

            status = 'Active' if ing.status.load_balancer.ingress else 'Pending'

            ingress_details = {
                'name': ing.metadata.name,
                'namespace': ing.metadata.namespace,
                'hostname': hostname,
                'ingress_class': ingress_class,
                'status': status,
                'creation_timestamp': ing.metadata.creation_timestamp.isoformat() if ing.metadata.creation_timestamp else 'N/A'
            }

            ingress_list.append(ingress_details)

        filtered_resources = ingress_list
        for key, value in filters.items():
            filtered_resources = [
                resource for resource in filtered_resources
                if str(resource.get(key, '')).lower() == str(value).lower()
            ]

        logger.info(f"Filtered ingresses count: {len(filtered_resources)}")
        return filtered_resources

    except Exception as e:
        logger.error(f"Error retrieving Ingress resources: {e}")
        traceback.print_exc()
        return generate_mock_ingresses()


def get_httproute_resources(filters=None, force_refresh=False):
    try:
        if not load_kubernetes_config():
            logger.warning("Cannot load Kubernetes configuration")
            return generate_mock_httproutes()

        filters = filters or {}
        custom_api = client.CustomObjectsApi()
        routes, _ = _list_gateway_api_resources(custom_api, 'httproutes', namespaced=True)

        route_list = []
        for route in routes.get('items', []):
            spec = route.get('spec', {})
            status_obj = route.get('status', {})
            hostnames = ', '.join(spec.get('hostnames', []) or ['N/A'])
            parent_refs = spec.get('parentRefs', []) or []
            parent_ref = ', '.join([pref.get('name', 'N/A') for pref in parent_refs]) or 'N/A'
            parent_ref_class = ', '.join([
                pref.get('sectionName') or pref.get('name', 'N/A')
                for pref in parent_refs
            ]) or 'N/A'
            parents_status = status_obj.get('parents', []) or []
            status = 'Active' if parents_status else 'Pending'

            route_list.append({
                'name': route.get('metadata', {}).get('name', 'N/A'),
                'namespace': route.get('metadata', {}).get('namespace', 'default'),
                'hostnames': hostnames,
                'parent_ref': parent_ref,
                'ingress_class': parent_ref_class,
                'status': status,
                'creation_timestamp': route.get('metadata', {}).get('creationTimestamp', 'N/A')
            })

        filtered_resources = route_list
        for key, value in filters.items():
            filtered_resources = [
                resource for resource in filtered_resources
                if str(resource.get(key, '')).lower() == str(value).lower()
            ]

        return filtered_resources
    except Exception as e:
        logger.error(f"Error retrieving HTTPRoute resources: {e}")
        traceback.print_exc()
        return generate_mock_httproutes()


def get_gateway_resources(filters=None, force_refresh=False):
    try:
        if not load_kubernetes_config():
            logger.warning("Cannot load Kubernetes configuration")
            return generate_mock_gateways()

        filters = filters or {}
        custom_api = client.CustomObjectsApi()
        gateways, _ = _list_gateway_api_resources(custom_api, 'gateways', namespaced=True)

        gateway_list = []
        for gateway in gateways.get('items', []):
            spec = gateway.get('spec', {})
            listeners = spec.get('listeners', []) or []
            listener_text = ', '.join([
                f"{listener.get('name', 'listener')}:{listener.get('port', 'N/A')}"
                for listener in listeners
            ]) or 'N/A'
            status_obj = gateway.get('status', {})
            status = 'Active' if (status_obj.get('addresses') or status_obj.get('listeners')) else 'Pending'

            gateway_list.append({
                'name': gateway.get('metadata', {}).get('name', 'N/A'),
                'namespace': gateway.get('metadata', {}).get('namespace', 'default'),
                'gateway_class': spec.get('gatewayClassName', 'N/A'),
                'ingress_class': spec.get('gatewayClassName', 'N/A'),
                'listeners': listener_text,
                'status': status,
                'creation_timestamp': gateway.get('metadata', {}).get('creationTimestamp', 'N/A')
            })

        filtered_resources = gateway_list
        for key, value in filters.items():
            filtered_resources = [
                resource for resource in filtered_resources
                if str(resource.get(key, '')).lower() == str(value).lower()
            ]

        return filtered_resources
    except Exception as e:
        logger.error(f"Error retrieving Gateway resources: {e}")
        traceback.print_exc()
        return generate_mock_gateways()


def get_gatewayclass_resources(filters=None, force_refresh=False):
    try:
        if not load_kubernetes_config():
            logger.warning("Cannot load Kubernetes configuration")
            return generate_mock_gatewayclasses()

        filters = filters or {}
        custom_api = client.CustomObjectsApi()
        gatewayclasses, _ = _list_gateway_api_resources(custom_api, 'gatewayclasses', namespaced=False)

        gatewayclass_list = []
        for gatewayclass in gatewayclasses.get('items', []):
            metadata = gatewayclass.get('metadata', {})
            spec = gatewayclass.get('spec', {})
            description = metadata.get('annotations', {}).get('description', 'N/A')
            status = 'Active' if gatewayclass.get('status') else 'Pending'

            gatewayclass_list.append({
                'name': metadata.get('name', 'N/A'),
                'namespace': 'cluster-wide',
                'controller': spec.get('controllerName', 'N/A'),
                'description': description,
                'status': status,
                'creation_timestamp': metadata.get('creationTimestamp', 'N/A')
            })

        filtered_resources = gatewayclass_list
        for key, value in filters.items():
            filtered_resources = [
                resource for resource in filtered_resources
                if str(resource.get(key, '')).lower() == str(value).lower()
            ]

        return filtered_resources
    except Exception as e:
        logger.error(f"Error retrieving GatewayClass resources: {e}")
        traceback.print_exc()
        return generate_mock_gatewayclasses()

def convert_dict_to_yaml(resource_dict):
    try:
        import yaml
        return yaml.dump(resource_dict, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.error(f"Error converting resource to YAML: {e}")
        return f"# Error generating YAML\n# {str(e)}"


def create_app(test_config=None):
    app = Flask(__name__, static_folder='static')
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        ping_timeout=30,
        ping_interval=10,
        async_mode='threading'
    )

    original_get_ingress_resources = get_ingress_resources
    original_get_httproute_resources = get_httproute_resources
    original_get_gateway_resources = get_gateway_resources
    original_get_gatewayclass_resources = get_gatewayclass_resources

    if test_config:
        def create_test_getter(config_key, default_resources):
            def test_get_resources(filters=None, force_refresh=False):
                mock_resources = test_config.get(config_key, default_resources)
                if filters:
                    mock_resources = [
                        resource for resource in mock_resources
                        if all(
                            str(resource.get(key, '')).lower() == str(value).lower()
                            for key, value in filters.items()
                        )
                    ]
                return mock_resources
            return test_get_resources

        globals()['get_ingress_resources'] = create_test_getter('mock_resources', [])
        globals()['get_httproute_resources'] = create_test_getter('mock_httproutes', [])
        globals()['get_gateway_resources'] = create_test_getter('mock_gateways', [])
        globals()['get_gatewayclass_resources'] = create_test_getter('mock_gatewayclasses', [])
    def convert_ingress_to_yaml(ingress):
        try:
            ingress_dict = ingress.to_dict()
            return convert_dict_to_yaml(ingress_dict)
        except Exception as e:
            logger.error(f"Error converting Ingress to YAML: {e}")
            return f"# Error generating YAML\n# {str(e)}"

    @app.route('/ingress/yaml/<namespace>/<name>')
    def get_ingress_yaml(namespace, name):
        try:
            load_kubernetes_config()
            networking_v1 = client.NetworkingV1Api()
            ingress = networking_v1.read_namespaced_ingress(name, namespace)
            yaml_content = convert_ingress_to_yaml(ingress)
            return jsonify({'yaml': yaml_content}), 200
        except Exception as e:
            logger.error(f"Error fetching Ingress YAML: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/httproute/yaml/<namespace>/<name>')
    def get_httproute_yaml(namespace, name):
        try:
            load_kubernetes_config()
            custom_api = client.CustomObjectsApi()
            route = _get_gateway_api_resource(
                custom_api,
                plural='httproutes',
                namespace=namespace,
                name=name
            )
            return jsonify({'yaml': convert_dict_to_yaml(route)}), 200
        except Exception as e:
            logger.error(f"Error fetching HTTPRoute YAML: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/gateway/yaml/<namespace>/<name>')
    def get_gateway_yaml(namespace, name):
        try:
            load_kubernetes_config()
            custom_api = client.CustomObjectsApi()
            gateway = _get_gateway_api_resource(
                custom_api,
                plural='gateways',
                namespace=namespace,
                name=name
            )
            return jsonify({'yaml': convert_dict_to_yaml(gateway)}), 200
        except Exception as e:
            logger.error(f"Error fetching Gateway YAML: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/gatewayclass/yaml/<name>')
    def get_gatewayclass_yaml(name):
        try:
            load_kubernetes_config()
            custom_api = client.CustomObjectsApi()
            gatewayclass = _get_gateway_api_resource(
                custom_api,
                plural='gatewayclasses',
                name=name
            )
            return jsonify({'yaml': convert_dict_to_yaml(gatewayclass)}), 200
        except Exception as e:
            logger.error(f"Error fetching GatewayClass YAML: {e}")
            return jsonify({'error': str(e)}), 500

    @app.teardown_appcontext
    def cleanup(exception=None):
        globals()['get_ingress_resources'] = original_get_ingress_resources
        globals()['get_httproute_resources'] = original_get_httproute_resources
        globals()['get_gateway_resources'] = original_get_gateway_resources
        globals()['get_gatewayclass_resources'] = original_get_gatewayclass_resources

    @app.route('/')
    def index():
        return render_template('index.html',
                             app_version=APP_VERSION,
                             git_commit=GIT_COMMIT[:7] if len(GIT_COMMIT) > 7 else GIT_COMMIT,
                             build_date=BUILD_DATE)

    @app.route('/version')
    def version_info():
        return jsonify({
            'version': APP_VERSION,
            'build_date': BUILD_DATE,
            'git_commit': GIT_COMMIT,
            'git_commit_short': GIT_COMMIT[:7] if len(GIT_COMMIT) > 7 else GIT_COMMIT
        }), 200

    @app.route('/health')
    def health_check():
        try:
            return jsonify({
                'status': 'healthy',
                'kubernetes_available': load_kubernetes_config(),
                'version': {
                    'app': APP_VERSION,
                    'build_date': BUILD_DATE,
                    'git_commit': GIT_COMMIT
                }
            }), 200
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e),
                'version': {
                    'app': APP_VERSION,
                    'build_date': BUILD_DATE,
                    'git_commit': GIT_COMMIT
                }
            }), 500

    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')
        try:
            ingresses = get_ingress_resources()
            httproutes = get_httproute_resources()
            gateways = get_gateway_resources()
            gatewayclasses = get_gatewayclass_resources()
            emit('ingress_update', ingresses)
            emit('httproute_update', httproutes)
            emit('gateway_update', gateways)
            emit('gatewayclass_update', gatewayclasses)
        except Exception as e:
            logger.error(f"Error on client connect: {e}")
            emit('ingress_update', generate_mock_ingresses())
            emit('httproute_update', generate_mock_httproutes())
            emit('gateway_update', generate_mock_gateways())
            emit('gatewayclass_update', generate_mock_gatewayclasses())

    @socketio.on('get_ingresses')
    def handle_get_ingresses(filters=None):
        try:
            if filters is None:
                filters = {}
            logger.info(f"Received filters: {filters}")
            ingresses = get_ingress_resources(filters)
            logger.info(f"Filtered ingresses count: {len(ingresses)}")
            emit('ingress_update', ingresses)
        except Exception as e:
            logger.error(f"Error getting ingresses: {e}")
            traceback.print_exc()
            emit('ingress_update', generate_mock_ingresses())

    @socketio.on('get_httproutes')
    def handle_get_httproutes(filters=None):
        try:
            filters = filters or {}
            resources = get_httproute_resources(filters)
            emit('httproute_update', resources)
        except Exception as e:
            logger.error(f"Error getting httproutes: {e}")
            traceback.print_exc()
            emit('httproute_update', generate_mock_httproutes())

    @socketio.on('get_gateways')
    def handle_get_gateways(filters=None):
        try:
            filters = filters or {}
            resources = get_gateway_resources(filters)
            emit('gateway_update', resources)
        except Exception as e:
            logger.error(f"Error getting gateways: {e}")
            traceback.print_exc()
            emit('gateway_update', generate_mock_gateways())

    @socketio.on('get_gatewayclasses')
    def handle_get_gatewayclasses(filters=None):
        try:
            filters = filters or {}
            resources = get_gatewayclass_resources(filters)
            emit('gatewayclass_update', resources)
        except Exception as e:
            logger.error(f"Error getting gatewayclasses: {e}")
            traceback.print_exc()
            emit('gatewayclass_update', generate_mock_gatewayclasses())

    # Skip background thread in test mode
    if not test_config:
        refresh_interval_seconds = get_refresh_interval_seconds()
        logger.info(
            "Starting background ingress refresh every %s seconds",
            refresh_interval_seconds
        )

        def background_update():
            while True:
                try:
                    ingresses = get_ingress_resources(force_refresh=True)
                    httproutes = get_httproute_resources(force_refresh=True)
                    gateways = get_gateway_resources(force_refresh=True)
                    gatewayclasses = get_gatewayclass_resources(force_refresh=True)
                    socketio.emit('ingress_update', ingresses)
                    socketio.emit('httproute_update', httproutes)
                    socketio.emit('gateway_update', gateways)
                    socketio.emit('gatewayclass_update', gatewayclasses)
                except Exception as e:
                    logger.error(f"Background update failed: {e}")
                time.sleep(refresh_interval_seconds)

        # Start background thread
        threading.Thread(target=background_update, daemon=True).start()

    return app, socketio

# Application entry point
if __name__ == '__main__':
    # Create the app
    app = Flask(__name__, static_folder='static')  # Add this line
    app, socketio = create_app()

    # Run the application
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True
    )

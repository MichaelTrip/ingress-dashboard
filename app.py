import logging
import os
import threading
import time
import traceback
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from kubernetes import client, config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global cache to improve performance
INGRESS_CACHE = {
    'resources': [],
    'last_updated': 0,
    'lock': threading.Lock()
}

def load_kubernetes_config():
    """
    Attempt to load Kubernetes configuration
    Supports:
    1. In-cluster configuration
    2. Local kubeconfig
    3. Custom kubeconfig path via environment variable
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

def get_ingress_resources(filters=None, force_refresh=False):
    """
    Retrieve Ingress resources with optional filtering
    """
    # Ensure Kubernetes configuration is loaded
    if not load_kubernetes_config():
        logger.warning("Cannot load Kubernetes configuration")
        return generate_mock_ingresses()

    current_time = time.time()

    with INGRESS_CACHE['lock']:
        # Refresh every 30 seconds or if forced
        if force_refresh or (current_time - INGRESS_CACHE['last_updated']) > 30:
            try:
                # Create Kubernetes API client
                networking_v1 = client.NetworkingV1Api()

                # Fetch ingress resources from all namespaces
                ingresses = networking_v1.list_ingress_for_all_namespaces()

                # Process and prepare ingress data
                ingress_list = []
                for ing in ingresses.items:
                    # Extract relevant information
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

                # Update cache
                INGRESS_CACHE['resources'] = ingress_list
                INGRESS_CACHE['last_updated'] = current_time

            except Exception as e:
                logger.error(f"Error retrieving Ingress resources: {e}")
                traceback.print_exc()
                return generate_mock_ingresses()

        # Apply filtering
        filtered_resources = INGRESS_CACHE['resources']
        if filters:
            filtered_resources = [
                resource for resource in filtered_resources
                if all(
                    str(resource.get(key, '')).lower() == str(value).lower()
                    for key, value in filters.items()
                )
            ]

        return filtered_resources if filtered_resources else generate_mock_ingresses()

def generate_mock_ingresses():
    """
    Generate mock Ingress resources for testing or when no resources are found
    """
    return [
        {
            'name': 'example-ingress-1',
            'namespace': 'default',
            'hostname': 'app1.example.com',
            'ingress_class': 'nginx',
            'status': 'Active',
            'creation_timestamp': time.time()
        },
        {
            'name': 'example-ingress-2',
            'namespace': 'kube-system',
            'hostname': 'app2.example.com',
            'ingress_class': 'traefik',
            'status': 'Pending',
            'creation_timestamp': time.time()
        }
    ]

def create_app(test_config=None):
    """
    Create and configure the Flask application
    """
    app = Flask(__name__)
    socketio = SocketIO(
app,
        cors_allowed_origins="*",
        ping_timeout=30,
        ping_interval=10,
        async_mode='threading'
    )

    # Explicitly define background_update with a reference to get_ingress_resources
    def background_update(get_ingress_resources_func):
        while True:
            try:
                ingresses = get_ingress_resources_func(force_refresh=True)
                socketio.emit('ingress_update', ingresses)
            except Exception as e:
                logger.error(f"Background update failed: {e}")
                traceback.print_exc()
            socketio.sleep(30)  # Update every 30 seconds

    @app.route('/health')
    def health_check():
        try:
            # Quick health check
            status = {
                'kubernetes_available': load_kubernetes_config(),
                'ingress_resources_count': len(get_ingress_resources())
            }
            return jsonify(status), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/')
    def index():
        return render_template('index.html')

    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')
        try:
            # Send initial data on connect with error handling
            ingresses = get_ingress_resources()
            socketio.emit('ingress_update', ingresses)
        except Exception as e:
            logger.error(f"Error on client connect: {e}")
            traceback.print_exc()
            socketio.emit('ingress_update', generate_mock_ingresses())

    @socketio.on('get_ingresses')
    def handle_get_ingresses(filters=None):
        try:
            ingresses = get_ingress_resources(filters)
            socketio.emit('ingress_update', ingresses)
        except Exception as e:
            logger.error(f"Error getting ingresses: {e}")
            traceback.print_exc()
            socketio.emit('ingress_update', generate_mock_ingresses())

    # Start background thread
    socketio.start_background_task(background_update, get_ingress_resources)

    return app, socketio

# Application entry point
if __name__ == '__main__':
    # Check if running in mock mode
    if os.getenv('MOCK_MODE', 'false').lower() == 'true':
        logger.info("Starting in MOCK development mode")
        app, socketio = create_app()
        # Use mock data generator directly
        def mock_background_update():
            while True:
                try:
                    mock_ingresses = generate_mock_ingresses()
                    socketio.emit('ingress_update', mock_ingresses)
                except Exception as e:
                    logger.error(f"Mock background update failed: {e}")
                socketio.sleep(30)  # Update every 30 seconds

        socketio.start_background_task(mock_background_update)
    else:
        logger.info("Starting in Kubernetes mode")
        app, socketio = create_app()

    # Run the application
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True
    )

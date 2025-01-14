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

def get_ingress_resources(filters=None, force_refresh=False):
    """
    Retrieve and filter Ingress resources
    """
    try:
        # Ensure Kubernetes configuration is loaded
        if not load_kubernetes_config():
            logger.warning("Cannot load Kubernetes configuration")
            return generate_mock_ingresses()

        # Ensure filters is a dictionary
        filters = filters or {}
        logger.info(f"Received filters: {filters}")

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

        # Apply filtering
        filtered_resources = ingress_list
        for key, value in filters.items():
            filtered_resources = [
                resource for resource in filtered_resources
                if str(resource.get(key, '')).lower() == str(value).lower()
            ]

        logger.info(f"Filtered ingresses count: {len(filtered_resources)}")
        return filtered_resources or generate_mock_ingresses()

    except Exception as e:
        logger.error(f"Error retrieving Ingress resources: {e}")
        traceback.print_exc()
        return generate_mock_ingresses()

def create_app():
    """
    Create and configure the Flask application
    """
    app = Flask(__name__)
    socketio = SocketIO(app, cors_allowed_origins="*")

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/health')
    def health_check():
        return jsonify({
            'status': 'healthy',
            'kubernetes_available': load_kubernetes_config()
        }), 200

    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')
        try:
            # Send initial data on connect
            ingresses = get_ingress_resources()
            emit('ingress_update', ingresses)
        except Exception as e:logger.error(f"Error on client connect: {e}")

    @socketio.on('get_ingresses')
    def handle_get_ingresses(filters=None):
        try:
            # Ensure filters is a dictionary
            if filters is None:
                filters = {}
            
            # Log received filters
            logger.info(f"Received filters: {filters}")

            # Retrieve and filter ingresses
            ingresses = get_ingress_resources(filters)
            
            # Log number of filtered ingresses
            logger.info(f"Filtered ingresses count: {len(ingresses)}")

            # Emit the filtered ingresses
            emit('ingress_update', ingresses)
        except Exception as e:
            logger.error(f"Error getting ingresses: {e}")
            traceback.print_exc()
            # Emit mock data or empty list in case of error
            emit('ingress_update', generate_mock_ingresses())

    def background_update():
        while True:
            try:
                ingresses = get_ingress_resources(force_refresh=True)
                socketio.emit('ingress_update', ingresses)
            except Exception as e:
                logger.error(f"Background update failed: {e}")
            time.sleep(30)  # Update every 30 seconds

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
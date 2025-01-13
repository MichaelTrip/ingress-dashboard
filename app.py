import logging
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from kubernetes import client, config
import threading
import time
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_detailed_ingress_resources(filters=None):
    try:
        # Try in-cluster configuration first
        config.load_incluster_config()
    except config.ConfigException:
        try:
            # Fallback to local kubeconfig
            config.load_kube_config()
        except Exception as e:
            logger.warning(f"Could not load Kubernetes config: {e}")
            return []

    # Create Kubernetes API client
    networking_v1 = client.NetworkingV1Api()

    try:
        # Fetch ingress resources from all namespaces
        ingresses = networking_v1.list_ingress_for_all_namespaces()
        ingress_list = []

        for ing in ingresses.items:
            # Detailed Ingress Information
            ingress_details = {
                'name': ing.metadata.name,
                'namespace': ing.metadata.namespace,
                'creation_timestamp': ing.metadata.creation_timestamp.isoformat() if ing.metadata.creation_timestamp else 'N/A',

                # Metadata
                'labels': dict(ing.metadata.labels) if ing.metadata.labels else {},
                'annotations': dict(ing.metadata.annotations) if ing.metadata.annotations else {},

                # Spec Details
                'ingress_class_name': ing.spec.ingress_class_name or 'Default',

                # Rules and Paths
                'rules': [],

                # Status Information
                'status': {
                    'status': 'Pending',
                    'load_balancer_ingress': []
                },

                # TLS Configuration
                'tls_configured': bool(ing.spec.tls)
            }

            # Detailed Rules Processing
            if ing.spec.rules:
                for rule in ing.spec.rules:
                    rule_details = {
                        'host': rule.host or 'N/A',
                        'paths': []
                    }

                    if rule.http and rule.http.paths:
                        for path in rule.http.paths:
                            path_details = {
                                'path': path.path or '/',
                                'path_type': path.path_type or 'Prefix',
                                'backend': {
                                    'service_name': path.backend.service.name if path.backend and path.backend.service else 'N/A',
                                    'service_port': path.backend.service.port.number if path.backend and path.backend.service and path.backend.service.port else 'N/A'
                                }
                            }
                            rule_details['paths'].append(path_details)

                    ingress_details['rules'].append(rule_details)

            # Status Processing
            if ing.status and ing.status.load_balancer and ing.status.load_balancer.ingress:
                ingress_details['status']['status'] = 'Active'
                for lb in ing.status.load_balancer.ingress:
                    ingress_details['status']['load_balancer_ingress'].append({
                        'ip': lb.ip,
                        'hostname': lb.hostname
                    })

            # Apply Filtering
            if filters:
                match = True
                for key, value in filters.items():
                    # Handle nested key filtering
                    keys = key.split('.')
                    current = ingress_details
                    for k in keys[:-1]:
                        current = current.get(k, {})

                    if current.get(keys[-1]) != value:
                        match = False
                        break

                if not match:
                    continue

            ingress_list.append(ingress_details)

        return ingress_list

    except Exception as e:
        logger.error(f"Error retrieving Ingress resources: {e}")
        return []

def create_app():
    app = Flask(__name__)
    socketio = SocketIO(app, cors_allowed_origins="*")

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/ingresses')
    def get_ingresses():
        # Extract filters from query parameters
        filters = {
            k: v for k, v in request.args.items()
            if k in ['namespace', 'ingress_class_name', 'status.status']
        }

        ingresses = get_detailed_ingress_resources(filters)
        return jsonify(ingresses)

    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')

    @socketio.on('get_ingresses')
    def handle_get_ingresses(filters=None):
        ingresses = get_detailed_ingress_resources(filters)
        emit('ingress_update', ingresses)

    # Background thread to periodically update clients
    def background_ingress_update():
        while True:
            try:
                ingresses = get_detailed_ingress_resources()
                socketio.emit('ingress_update', ingresses)
            except Exception as e:
                logger.error(f"Error in background update: {e}")
            time.sleep(30)  # Update every 30 seconds

    # Start background thread
    threading.Thread(target=background_ingress_update, daemon=True).start()

    return app, socketio

if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, host='0.0.0.0', port=5000)

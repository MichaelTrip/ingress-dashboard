import logging
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from kubernetes import client, config
import threading
import time
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variable to track application readiness
IS_READY = False

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

        # Rest of the existing implementation remains the same...
        # (previous get_detailed_ingress_resources code)

        return ingress_list

    except Exception as e:
        logger.error(f"Error retrieving Ingress resources: {e}")
        return []

def create_app():
    app = Flask(__name__)
    socketio = SocketIO(app, cors_allowed_origins="*")

    @app.route('/health')
    def health_check():
        """
        Liveness probe: Always returns 200 OK
        Indicates the application is running
        """
        return 'OK', 200

    @app.route('/ready')
    def readiness_check():
        """
        Readiness probe: Checks if the application is ready to serve traffic
        """
        global IS_READY
        try:
            # Check Kubernetes connectivity
            try:
                config.load_kube_config()
                networking_v1 = client.NetworkingV1Api()
                # Try to list namespaces to verify connectivity
                networking_v1.list_namespaced_ingress(namespace='default')
            except Exception as e:
                logger.error(f"Kubernetes connectivity check failed: {e}")
                IS_READY = False
                return jsonify({
                    'status': 'not-ready',
                    'reason': 'Kubernetes connectivity failed'
                }), 503

            # Check if initial resource fetch is complete
            if not IS_READY:
                return jsonify({
                    'status': 'not-ready',
                    'reason': 'Initial resource loading'
                }), 503

            return jsonify({
                'status': 'ready',
                'message': 'Application is ready to serve traffic'
            }), 200

        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            IS_READY = False
            return jsonify({
                'status': 'not-ready',
                'reason': str(e)
            }), 503

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
        global IS_READY
        while True:
            try:
                ingresses = get_detailed_ingress_resources()
                socketio.emit('ingress_update', ingresses)
                IS_READY = True  # Mark as ready after first successful update
            except Exception as e:
                logger.error(f"Error in background update: {e}")
                IS_READY = False
            time.sleep(30)  # Update every 30 seconds

    # Start background thread
    threading.Thread(target=background_ingress_update, daemon=True).start()

    return app, socketio

if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, host='0.0.0.0', port=5000)

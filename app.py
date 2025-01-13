import logging
from flask import Flask, render_template, jsonify
from kubernetes import client, config
import socket
import os


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_ingress_resources(mock_resources=None):
    if mock_resources is not None:
        return mock_resources

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

        # If no ingresses found, return default message
        if not ingresses.items:
            return [{
                'name': 'No Ingress',
                'namespace': 'N/A',
                'hostname': 'N/A',
                'ingress_class': 'N/A',
                'status': 'No Resources'
            }]

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

            ingress_list.append({
                'name': ing.metadata.name,
                'namespace': ing.metadata.namespace,
                'hostname': hostname,
                'ingress_class': ingress_class,
                'status': status
            })

        logger.info(f"Retrieved {len(ingress_list)} Ingress resources")
        return ingress_list

    except Exception as e:
        logger.error(f"Error retrieving Ingress resources: {e}")
        return [{
            'name': 'Error',
            'namespace': 'N/A',
            'hostname': 'N/A',
            'ingress_class': 'N/A',
            'status': 'Error Retrieving Resources'
        }]


def create_app(test_config=None):
    app = Flask(__name__)

    @app.route('/')
    def index():
        try:
            # If test_config is provided, use mock resources
            mock_resources = test_config.get('mock_resources') if test_config else None
            ingresses = get_ingress_resources(mock_resources)

            # Add debugging information
            if len(ingresses) == 1 and ingresses[0]['status'] in ['No Resources', 'Error Retrieving Resources']:
                logger.warning("No Ingress resources found or error occurred")

            return render_template('index.html', ingresses=ingresses)
        except Exception as e:
            logger.error(f"Error rendering index: {e}")
            return render_template('error.html', error=str(e)), 500

    @app.route('/health')
    def health_check():
        try:
            # Check network connectivity
            socket.create_connection(("8.8.8.8", 53), timeout=3)

            # Check Kubernetes configuration
            try:
                config.load_incluster_config()
            except config.ConfigException:
                try:
                    config.load_kube_config()
                except Exception:
                    return jsonify({
                        'status': 'unhealthy',
                        'message': 'Kubernetes configuration failed'
                    }), 500

            # Attempt to list namespaces
            try:
                core_v1 = client.CoreV1Api()
                core_v1.list_namespace()
            except Exception as e:
                return jsonify({
                    'status': 'unhealthy',
                    'message': f'Cannot list namespaces: {str(e)}'
                }), 500

            # Basic system check
            health_status = {
                'status': 'healthy',
                'network': 'connected',
                'kubernetes': 'configured',
                'ingress_resources': len(get_ingress_resources())
            }

            return jsonify(health_status), 200

        except (socket.error, Exception) as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'message': str(e)
            }), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run()

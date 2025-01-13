import logging
from flask import Flask, render_template
from kubernetes import client, config


logger = logging.getConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_ingress_resources():
    try:
        # Try in-cluster configuration first
        config.load_incluster_config()
    except config.ConfigException:
        # Fallback to local kubeconfig
        config.load_kube_config()

    # Create Kubernetes API client
    networking_v1 = client.NetworkingV1Api()

    # Fetch ingress resources from all namespaces
    try:
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
                getattr(ing.spec, 'backend', None).resource.kind
                if getattr(ing.spec, 'backend', None)
                else 'Default'
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
        return []


def create_app():
    app = Flask(__name__)

    @app.route('/')
    def index():
        try:
            ingresses = get_ingress_resources()
            return render_template('index.html', ingresses=ingresses)
        except Exception as e:
            logger.error(f"Error rendering index: {e}")
            return render_template('error.html', error=str(e)), 500

    @app.route('/health')
    def health_check():
        return 'OK', 200

    return app


if __name__ == '__main__':
    app = create_app()
    app.run()

import logging
from flask import Flask, render_template, jsonify
from kubernetes import client, config
import socket


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_ingress_resources(mock_resources=None):
    # Previous implementation remains the same
    ...


def create_app(test_config=None):
    app = Flask(__name__)

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

            # Basic system check
            health_status = {
                'status': 'healthy',
                'network': 'connected',
                'kubernetes': 'configured'
            }

            return jsonify(health_status), 200

        except (socket.error, Exception) as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'message': str(e)
            }), 500

    # Rest of your application routes remain the same
    @app.route('/')
    def index():
        try:
            mock_resources = test_config.get('mock_resources') if test_config else None
            ingresses = get_ingress_resources(mock_resources)
            return render_template('index.html', ingresses=ingresses)
        except Exception as e:
            logger.error(f"Error rendering index: {e}")
            return render_template('error.html', error=str(e)), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run()

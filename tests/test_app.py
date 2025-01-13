import pytest
from app import create_app


@pytest.fixture
def client():
    # Create mock Ingress resources for testing
    test_config = {
        'mock_resources': [
            {
                'name': 'test-ingress',
                'namespace': 'default',
                'hostname': 'example.com',
                'ingress_class': 'nginx',
                'status': 'Active'
            }
        ]
    }

    app = create_app(test_config)
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client


def test_index_route(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'test-ingress' in response.data
    assert b'example.com' in response.data


def test_health_route(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.data == b'OK'

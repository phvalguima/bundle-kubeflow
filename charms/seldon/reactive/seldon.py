import os

from charmhelpers.core import hookenv
from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not
from subprocess import run

from pathlib import Path


@when('charm.seldon.started')
def charm_ready():
    layer.status.active('')


@when('layer.docker-resource.oci-image.changed', 'config.changed')
def update_image():
    clear_flag('charm.seldon.started')


@when('layer.docker-resource.oci-image.available')
@when_not('charm.seldon.started')
def start_charm():
    layer.status.maintenance('configuring container')

    config = hookenv.config()
    image_info = layer.docker_resource.get_info('oci-image')
    model = os.environ['JUJU_MODEL_NAME']

    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:4096",
            "-keyout",
            "key.pem",
            "-out",
            "cert.pem",
            "-days",
            "365",
            "-subj",
            f"/CN=webhook-server-service.{model}.svc",
            "-nodes",
        ],
        check=True,
    )

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'seldon-cluster-manager',
                    'command': ['/manager'],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'ports': [
                        {'name': 'metrics', 'containerPort': config['metrics-port']},
                        {'name': 'webhook', 'containerPort': config['webhook-port']},
                    ],
                    'config': {
                        'POD_NAMESPACE': model,
                        'SECRET_NAME': 'seldon-operator-webhook-server-secret',
                        'AMBASSADOR_ENABLED': 'true',
                        'AMBASSADOR_SINGLE_NAMESPACE': 'false',
                        'ENGINE_CONTAINER_IMAGE_AND_VERSION': 'docker.io/seldonio/engine:0.3.0',
                        'ENGINE_CONTAINER_IMAGE_PULL_POLICY': 'IfNotPresent',
                        'ENGINE_CONTAINER_SERVICE_ACCOUNT_NAME': 'default',
                        'ENGINE_CONTAINER_USER': '8888',
                        'PREDICTIVE_UNIT_SERVICE_PORT': '9000',
                        'ENGINE_SERVER_GRPC_PORT': '5001',
                        'ENGINE_SERVER_PORT': '8000',
                        'ENGINE_PROMETHEUS_PATH': 'prometheus',
                        'ISTIO_ENABLED': 'false',
                        'ISTIO_GATEWAY': 'kubeflow-gateway',
                    },
                    'files': [
                        {
                            'name': 'cert',
                            'mountPath': '/tmp/cert',
                            'files': {
                                'cert.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        }
                    ],
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.seldon.started')

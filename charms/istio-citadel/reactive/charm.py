import os
from subprocess import run

import yaml
from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not
from pathlib import Path


@when('charm.started')
def charm_ready():
    layer.status.active('')


@when('layer.docker-resource.oci-image.changed')
def update_image():
    clear_flag('charm.started')


@when('layer.docker-resource.oci-image.available')
@when_not('charm.started')
def start_charm():
    layer.status.maintenance('configuring container')

    image_info = layer.docker_resource.get_info('oci-image')

    model = os.environ['JUJU_MODEL_NAME']

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'citadel',
                    'args': [
                        '--append-dns-names=true',
                        '--grpc-port=8060',
                        '--grpc-hostname=citadel',
                        f'--citadel-storage-namespace={model}',
                        f'--custom-dns-names=istio-pilot-service-account.{model}:istio-pilot.{model}',
                        '--monitoring-port=15014',
                        '--self-signed-ca=true',
                    ],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'livenessProbe': {
                        'httpGet': {'path': '/version', 'port': 15014},
                        'initialDelaySeconds': 5,
                        'periodSeconds': 5,
                    },
                    'ports': [{'name': 'dummy', 'containerPort': 9999}],
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')

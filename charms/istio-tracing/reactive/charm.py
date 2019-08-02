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

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'jaeger',
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'ports': [
                        {'name': 'http', 'containerPort': 9411},
                        {'name': 'query-http', 'containerPort': 16686},
                        {'name': 'agnt-zpkn-thrft', 'containerPort': 5775, 'protocol': 'UDP'},
                        {'name': 'agent-compact', 'containerPort': 6831, 'protocol': 'UDP'},
                        {'name': 'agent-binary', 'containerPort': 6832, 'protocol': 'UDP'},
                    ],
                    'config': {
                        'POD_NAMESPACE': os.environ['JUJU_MODEL_NAME'],
                        'COLLECTOR_ZIPKIN_HTTP_PORT': '9411',
                        'MEMORY_MAX_TRACES': '50000',
                        'QUERY_BASE_PATH': '/jaeger',
                    },
                    'livenessProbe': {'httpGet': {'path': '/', 'port': 16686}},
                    'readinessProbe': {'httpGet': {'path': '/', 'port': 16686}},
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')

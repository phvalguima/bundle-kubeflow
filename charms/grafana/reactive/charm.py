from glob import glob

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
                    'name': 'grafana',
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'config': {
                        'GRAFANA_PORT': '3000',
                        'GF_AUTH_BASIC_ENABLED': 'false',
                        'GF_AUTH_ANONYMOUS_ENABLED': 'true',
                        'GF_AUTH_ANONYMOUS_ORG_ROLE': 'Admin',
                        'GF_PATHS_DATA': '/tmp/grafana',
                    },
                    'readinessProbe': {'httpGet': {'path': '/login', 'port': 3000}},
                    'ports': [{'name': 'http', 'containerPort': 3000}],
                    'files': [
                        {
                            'name': 'dashboards',
                            'mountPath': '/var/lib/grafana/dashboards/istio/',
                            'files': {
                                Path(filename).name: Path(filename).read_text(encoding='utf-8')
                                for filename in glob('files/*.json')
                            },
                        },
                        {
                            'name': 'datasources',
                            'mountPath': '/etc/grafana/provisioning/datasources/',
                            'files': {
                                'datasources.yaml': Path('files/datasources.yaml').read_text()
                            },
                        },
                        {
                            'name': 'providers',
                            'mountPath': '/etc/grafana/provisioning/dashboards/',
                            'files': {
                                'dashboardproviders.yaml': Path(
                                    'files/dashboardproviders.yaml'
                                ).read_text()
                            },
                        },
                    ],
                    # 'securityContext': {'fsGroup': 472, 'runAsUser': 472},
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')

import os
from subprocess import run

import yaml
from charmhelpers.core import hookenv
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

    crds = yaml.safe_load_all(Path("files/crd.yaml").read_text())

    hookenv.log(os.environ)

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
            "/CN=localhost",
            "-nodes",
        ],
        check=True,
    )

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'galley',
                    'command': [
                        '/usr/local/bin/galley',
                        'server',
                        '--meshConfigFile=/etc/mesh-config/mesh',
                        '--livenessProbeInterval=1s',
                        '--livenessProbePath=/healthliveness',
                        '--readinessProbePath=/healthready',
                        '--readinessProbeInterval=1s',
                        '--deployment-namespace=istio-system',
                        '--insecure=true',
                        '--validation-webhook-config-file',
                        '/etc/config/validatingwebhookconfiguration.yaml',
                        '--monitoringPort=15014',
                        '--log_output_level=default:info',
                    ],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'livenessProbe': {
                        'exec': {
                            'command': [
                                '/usr/local/bin/galley',
                                'probe',
                                '--probe-path=/healthliveness',
                                '--interval=10s',
                            ]
                        },
                        'initialDelaySeconds': 5,
                        'periodSeconds': 5,
                    },
                    'ports': [
                        {'name': 'validation', 'containerPort': 443},
                        {'name': 'monitoring', 'containerPort': 15014},
                        {'name': 'grpc-mcp', 'containerPort': 9901},
                    ],
                    'readinessProbe': {
                        'exec': {
                            'command': [
                                '/usr/local/bin/galley',
                                'probe',
                                '--probe-path=/healthready',
                                '--interval=10s',
                            ]
                        },
                        'initialDelaySeconds': 5,
                        'periodSeconds': 5,
                    },
                    'files': [
                        {
                            'name': 'mesh-config',
                            'mountPath': '/etc/mesh-config',
                            'files': {
                                'mesh': Path('files/mesh.yaml').read_text(),
                                'meshNetworks': 'networks: {}',
                            },
                        },
                        {
                            'name': 'config',
                            'mountPath': '/etc/config',
                            'files': {
                                'validatingwebhookconfiguration.yaml': Path(
                                    'files/validatingwebhookconfiguration.yaml'
                                ).read_text()
                            },
                        },
                        {
                            'name': 'certs',
                            'mountPath': '/etc/certs',
                            'files': {
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                    ],
                }
            ],
            'customResourceDefinitions': {crd['metadata']['name']: crd['spec'] for crd in crds},
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')

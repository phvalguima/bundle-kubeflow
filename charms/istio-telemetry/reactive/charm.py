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


@when('layer.docker-resource.mixer-image.available', 'layer.docker-resource.proxy-image.available')
@when_not('charm.started')
def start_charm():
    layer.status.maintenance('configuring container')

    mixer_image = layer.docker_resource.get_info('mixer-image')
    proxy_image = layer.docker_resource.get_info('proxy-image')

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
            "/CN=localhost",
            "-nodes",
        ],
        check=True,
    )

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'mixer',
                    'args': [
                        '--monitoringPort=15014',
                        '--address',
                        'unix:///sock/mixer.socket',
                        '--log_output_level=default:info',
                        f'--configStoreURL=mcp://istio-galley.{model}.svc:9901',
                        f'--configDefaultNamespace={model}',
                        '--useAdapterCRDs=true',
                        '--trace_zipkin_url=http://zipkin:9411/api/v1/spans',
                        '--averageLatencyThreshold',
                        '100ms',
                        '--loadsheddingMode',
                        'enforce',
                    ],
                    'imageDetails': {
                        'imagePath': mixer_image.registry_path,
                        'username': mixer_image.username,
                        'password': mixer_image.password,
                    },
                    'config': {'GODEBUG': 'gctrace=1', 'GOMAXPROCS': '6'},
                    'livenessProbe': {
                        'httpGet': {'path': '/version', 'port': 15014},
                        'initialDelaySeconds': 5,
                        'periodSeconds': 5,
                    },
                    'ports': [
                        {'name': 'port-1', 'containerPort': 15014},
                        {'name': 'port-2', 'containerPort': 42422},
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
                            'name': 'istio-certs',
                            'mountPath': '/etc/certs',
                            'files': {
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                        {
                            'name': 'telemetry-adapter-secret',
                            'mountPath': '/var/run/secrets/istio.io/telemetry/adapter',
                            'files': {},
                        },
                    ],
                },
                {
                    'name': 'istio-proxy',
                    'args': [
                        'proxy',
                        '--domain',
                        f'{model}.svc.cluster.local',
                        '--serviceCluster',
                        'istio-telemetry',
                        '--templateFile',
                        '/etc/istio/proxy/envoy_telemetry.yaml.tmpl',
                        '--controlPlaneAuthPolicy',
                        'NONE',
                    ],
                    'imageDetails': {
                        'imagePath': proxy_image.registry_path,
                        'username': proxy_image.username,
                        'password': proxy_image.password,
                    },
                    'config': {
                        'POD_NAME': 'metadata.name',
                        'POD_NAMESPACE': model,
                        'INSTANCE_IP': 'status.podIP',
                    },
                    'ports': [
                        {'name': 'port-3', 'containerPort': 9091},
                        {'name': 'port-4', 'containerPort': 15004},
                        {'name': 'http-envoy-prom', 'containerPort': 15090, 'protocol': 'TCP'},
                    ],
                    'files': [
                        {
                            'name': 'istio-certs',
                            'mountPath': '/etc/certs',
                            'files': {
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        }
                    ],
                },
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')

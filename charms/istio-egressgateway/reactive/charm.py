import os
from subprocess import run

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

    namespace = os.environ['JUJU_MODEL_NAME']

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
                    'name': 'istio-proxy',
                    'args': [
                        'proxy',
                        'router',
                        '--domain',
                        f'{namespace}.svc.cluster.local',
                        '--log_output_level=default:info',
                        '--drainDuration',
                        '45s',
                        '--parentShutdownDuration',
                        '1m0s',
                        '--connectTimeout',
                        '10s',
                        '--serviceCluster',
                        'istio-egressgateway',
                        '--zipkinAddress',
                        'zipkin:9411',
                        '--proxyAdminPort',
                        '15000',
                        '--statusPort',
                        '15020',
                        '--controlPlaneAuthPolicy',
                        'NONE',
                        '--discoveryAddress',
                        'istio-pilot:15010',
                    ],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'config': {
                        'POD_NAME': 'metadata.name',
                        'POD_NAMESPACE': namespace,
                        'INSTANCE_IP': 'status.podIP',
                        'HOST_IP': 'status.hostIP',
                        'ISTIO_META_POD_NAME': 'metadata.name',
                        'ISTIO_META_CONFIG_NAMESPACE': 'metadata.namespace',
                        'ISTIO_META_ROUTER_MODE': 'sni-dnat',
                    },
                    'readinessProbe': {
                        'failureThreshold': 30,
                        'httpGet': {'path': '/healthz/ready', 'port': 15020, 'scheme': 'HTTP'},
                        'initialDelaySeconds': 1,
                        'periodSeconds': 2,
                        'successThreshold': 1,
                        'timeoutSeconds': 1,
                    },
                    'ports': [
                        {'name': 'http', 'containerPort': 80},
                        {'name': 'https', 'containerPort': 443},
                        {'name': 'tls', 'containerPort': 15443},
                        {'name': 'envoy-prom', 'containerPort': 15090},
                    ],
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
                            'name': 'egressgateway-certs',
                            'mountPath': '/etc/istio/egressgateway-certs',
                            'files': {
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                        {
                            'name': 'egressgateway-ca-certs',
                            'mountPath': '/etc/istio/egressgateway-ca-certs',
                            'files': {
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                    ],
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')
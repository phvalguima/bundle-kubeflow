import os
from pathlib import Path
from subprocess import run

import yaml
from charmhelpers.core import hookenv
from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not


@when('charm.started')
def charm_ready():
    layer.status.active('')


@when('istio-pilot.available')
def configure_http(http):
    http.configure(port=15010, hostname=hookenv.application_name())


@when('layer.docker-resource.oci-image.changed')
def update_image():
    clear_flag('charm.started')


@when('layer.docker-resource.pilot-image.available', 'layer.docker-resource.proxy-image.available')
@when_not('charm.started')
def start_charm():
    layer.status.maintenance('configuring container')

    pilot_image = layer.docker_resource.get_info('pilot-image')
    proxy_image = layer.docker_resource.get_info('proxy-image')

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

    mesh = yaml.dump(
        {
            'disablePolicyChecks': False,
            'enableTracing': True,
            'accessLogFile': '/dev/stdout',
            'accessLogFormat': '',
            'accessLogEncoding': 'TEXT',
            'mixerCheckServer': f'istio-policy.{namespace}.svc.cluster.local:9091',
            'mixerReportServer': f'istio-telemetry.{namespace}.svc.cluster.local:9091',
            'policyCheckFailOpen': False,
            'ingressService': 'istio-ingressgateway',
            'connectTimeout': '10s',
            'dnsRefreshRate': '5s',
            'sdsUdsPath': None,
            'enableSdsTokenMount': False,
            'sdsUseK8sSaJwt': False,
            'trustDomain': None,
            'outboundTrafficPolicy': {'mode': 'ALLOW_ANY'},
            'localityLbSetting': {},
            'rootNamespace': namespace,
            'configSources': [
                {'address': f'istio-galley.{namespace}.svc:9901'}
            ],
            'defaultConfig': {
                'connectTimeout': '10s',
                'configPath': '/etc/istio/proxy',
                'binaryPath': '/usr/local/bin/envoy',
                'serviceCluster': 'istio-proxy',
                'drainDuration': '45s',
                'parentShutdownDuration': '1m0s',
                'proxyAdminPort': 15000,
                'concurrency': 2,
                'tracing': {
                    'zipkin': {'address': f'zipkin.{namespace}:9411'}
                },
                'controlPlaneAuthPolicy': 'NONE',
                'discoveryAddress': f'{hookenv.service_name()}.{namespace}:15010',
            },
        }
    )

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'discovery',
                    'args': [
                        'discovery',
                        '--monitoringAddr=:15014',
                        '--log_output_level=default:info',
                        '--domain',
                        'cluster.local',
                        '--secureGrpcAddr',
                        '',
                        '--keepaliveMaxServerConnectionAge',
                        '30m',
                    ],
                    'imageDetails': {
                        'imagePath': pilot_image.registry_path,
                        'username': pilot_image.username,
                        'password': pilot_image.password,
                    },
                    'config': {
                        'POD_NAME': 'metadata.name',
                        'POD_NAMESPACE': namespace,
                        'GODEBUG': 'gctrace=1',
                        'PILOT_PUSH_THROTTLE': '100',
                        'PILOT_TRACE_SAMPLING': '100',
                        'PILOT_DISABLE_XDS_MARSHALING_TO_ANY': '1',
                    },
                    'readinessProbe': {
                        'httpGet': {'path': '/ready', 'port': 8080},
                        'initialDelaySeconds': 5,
                        'periodSeconds': 30,
                        'timeoutSeconds': 5,
                    },
                    'ports': [
                        {'name': 'http-leg-disc', 'containerPort': 8080},
                        {'name': 'grpc-xds', 'containerPort': 15010},
                    ],
                    'files': [
                        {
                            'name': 'config-volume',
                            'mountPath': '/etc/istio/config',
                            'files': {
                                'mesh': mesh,
                                'meshNetworks': 'networks: {}',
                            },
                        },
                        {
                            'name': 'istio-certs1',
                            'mountPath': '/etc/certs',
                            'files': {
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                    ],
                },
                {
                    'name': 'istio-proxy',
                    'args': [
                        'proxy',
                        '--domain',
                        f'{namespace}.svc.cluster.local',
                        '--serviceCluster',
                        hookenv.service_name(),
                        '--templateFile',
                        '/etc/istio/proxy/envoy_pilot.yaml.tmpl',
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
                        'POD_NAMESPACE': namespace,
                        'INSTANCE_IP': 'status.podIP',
                    },
                    'ports': [
                        {'name': 'http-1', 'containerPort': 15003},
                        {'name': 'http-2', 'containerPort': 15005},
                        {'name': 'http-3', 'containerPort': 15007},
                        {'name': 'https-xds', 'containerPort': 15011},
                    ],
                    'files': [
                        {
                            'name': 'istio-certs',
                            'mountPath': '/etc/certs',
                            'files': {
                                'root-cert.pem': Path('cert.pem').read_text(),
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
